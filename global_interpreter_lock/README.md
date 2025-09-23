#  Global Interpreter Lock

## Brief overview of python internals
- One runtime with a runtime state
- One or moore interpreters each with an interpreter state 
- interpreter takes code objects and turns them into frame objects
- each interpreter has one or more threads each with a thread state (in a linked list)
- frame objects are executed in a frame stack
- values are referenced in a value stack
- interpreter state stores linked 

## How to get around it (Without multiprocess)
```{c}
PY_BEGIN_ALLOW_THREADS // set thread state to null and drop gil
#some stuff
Py_END_ALLOW_THREADS // get thread state back and take gil
```

Standard library does this for making requests, interacting with hardware,
reading files, etc.

Numpy does this when doing math.

We can do this in our C/Rust extensions/

## What the GIL does not prevent
```{python}
while True:
    if my_list:                 # Thread A and B can both see non-empty
        item = my_list.pop()    # One succeeds; the other may raise IndexError
        process(item)
```

[py_core_gil.h](https://github.com/python/cpython/blob/04c7f362055477efeaf3d539da30a608cdbbdc1e/Include/internal/pycore_gil.h#L22)

```{c}
struct _gil_runtime_state {
#ifdef Py_GIL_DISABLED
    /* If this GIL is disabled, enabled == 0.

       If this GIL is enabled transiently (most likely to initialize a module
       of unknown safety), enabled indicates the number of active transient
       requests.

       If this GIL is enabled permanently, enabled == INT_MAX.

       It must not be modified directly; use _PyEval_EnableGILTransiently(),
       _PyEval_EnableGILPermanently(), and _PyEval_DisableGIL()

       It is always read and written atomically, but a thread can assume its
       value will be stable as long as that thread is attached or knows that no
       other threads are attached (e.g., during a stop-the-world.). */
    int enabled;
#endif
    /* microseconds (the Python API uses seconds, though) */
    unsigned long interval;
    /* Last PyThreadState holding / having held the GIL. This helps us
       know whether anyone else was scheduled after we dropped the GIL. */
    PyThreadState* last_holder;
    /* Whether the GIL is already taken (-1 if uninitialized). This is
       atomic because it can be read without any lock taken in ceval.c. */
    int locked; 
    /* Number of GIL switches since the beginning. */
    unsigned long switch_number;
    /* This condition variable allows one or several threads to wait
       until the GIL is released. In addition, the mutex also protects
       the above variables. */
    PyCOND_T cond;
    PyMUTEX_T mutex;
#ifdef FORCE_SWITCHING
    /* This condition variable helps the GIL-releasing thread wait for
       a GIL-awaiting thread to be scheduled and take the GIL. */
    PyCOND_T switch_cond;
    PyMUTEX_T switch_mutex;
#endif
};
```

[ceval_gil.h](https://github.com/python/cpython/blob/b4ec17488eedec36d3c05fec127df71c0071f6cb/Python/ceval_gil.h#L194)
```{c}
/* Take the GIL.

   The function saves errno at entry and restores its value at exit.

   tstate must be non-NULL. */
static void
take_gil(PyThreadState *tstate)
{
    int err = errno;

    assert(tstate != NULL);

    if (_PyThreadState_MustExit(tstate)) {
        /* bpo-39877: If Py_Finalize() has been called and tstate is not the
           thread which called Py_Finalize(), exit immediately the thread.

           This code path can be reached by a daemon thread after Py_Finalize()
           completes. In this case, tstate is a dangling pointer: points to
           PyThreadState freed memory. */
        PyThread_exit_thread();
    }

    assert(_PyThreadState_CheckConsistency(tstate));
    PyInterpreterState *interp = tstate->interp;
    struct _ceval_runtime_state *ceval = &interp->runtime->ceval;
    struct _ceval_state *ceval2 = &interp->ceval;
    struct _gil_runtime_state *gil = &ceval->gil;

    /* Check that _PyEval_InitThreads() was called to create the lock */
    assert(gil_created(gil));

    MUTEX_LOCK(gil->mutex);

    if (!_Py_atomic_load_relaxed(&gil->locked)) {
        goto _ready;
    }

    int drop_requested = 0;
    while (_Py_atomic_load_relaxed(&gil->locked)) {
        unsigned long saved_switchnum = gil->switch_number;

        unsigned long interval = (gil->interval >= 1 ? gil->interval : 1);
        int timed_out = 0;
        COND_TIMED_WAIT(gil->cond, gil->mutex, interval, timed_out);

        /* If we timed out and no switch occurred in the meantime, it is time
           to ask the GIL-holding thread to drop it. */
        if (timed_out &&
            _Py_atomic_load_relaxed(&gil->locked) &&
            gil->switch_number == saved_switchnum)
        {
            if (_PyThreadState_MustExit(tstate)) {
                MUTEX_UNLOCK(gil->mutex);
                // gh-96387: If the loop requested a drop request in a previous
                // iteration, reset the request. Otherwise, drop_gil() can
                // block forever waiting for the thread which exited. Drop
                // requests made by other threads are also reset: these threads
                // may have to request again a drop request (iterate one more
                // time).
                if (drop_requested) {
                    RESET_GIL_DROP_REQUEST(interp);
                }
                PyThread_exit_thread();
            }
            assert(_PyThreadState_CheckConsistency(tstate));

            SET_GIL_DROP_REQUEST(interp);
            drop_requested = 1;
        }
    }

_ready:
#ifdef FORCE_SWITCHING
    /* This mutex must be taken before modifying gil->last_holder:
       see drop_gil(). */
    MUTEX_LOCK(gil->switch_mutex);
#endif
    /* We now hold the GIL */
    _Py_atomic_store_relaxed(&gil->locked, 1);
    _Py_ANNOTATE_RWLOCK_ACQUIRED(&gil->locked, /*is_write=*/1);

    if (tstate != (PyThreadState*)_Py_atomic_load_relaxed(&gil->last_holder)) {
        _Py_atomic_store_relaxed(&gil->last_holder, (uintptr_t)tstate);
        ++gil->switch_number;
    }

#ifdef FORCE_SWITCHING
    COND_SIGNAL(gil->switch_cond);
    MUTEX_UNLOCK(gil->switch_mutex);
#endif

    if (_PyThreadState_MustExit(tstate)) {
        /* bpo-36475: If Py_Finalize() has been called and tstate is not
           the thread which called Py_Finalize(), exit immediately the
           thread.

           This code path can be reached by a daemon thread which was waiting
           in take_gil() while the main thread called
           wait_for_thread_shutdown() from Py_Finalize(). */
        MUTEX_UNLOCK(gil->mutex);
        drop_gil(ceval, ceval2, tstate);
        PyThread_exit_thread();
    }
    assert(_PyThreadState_CheckConsistency(tstate));

    if (_Py_atomic_load_relaxed(&ceval2->gil_drop_request)) {
        RESET_GIL_DROP_REQUEST(interp);
    }
    else {
        /* bpo-40010: eval_breaker should be recomputed to be set to 1 if there
           is a pending signal: signal received by another thread which cannot
           handle signals.

           Note: RESET_GIL_DROP_REQUEST() calls COMPUTE_EVAL_BREAKER(). */
        COMPUTE_EVAL_BREAKER(interp, ceval, ceval2);
    }

    /* Don't access tstate if the thread must exit */
    if (tstate->async_exc != NULL) {
        _PyEval_SignalAsyncExc(tstate->interp);
    }

    MUTEX_UNLOCK(gil->mutex);

    errno = err;
}
```

[ceval_gil.h](https://github.com/python/cpython/blob/b4ec17488eedec36d3c05fec127df71c0071f6cb/Python/ceval_gil.h#L146)
```{c}
static void
drop_gil(struct _ceval_runtime_state *ceval, struct _ceval_state *ceval2,
         PyThreadState *tstate)
{
    struct _gil_runtime_state *gil = &ceval->gil;
    if (!_Py_atomic_load_relaxed(&gil->locked)) {
        Py_FatalError("drop_gil: GIL is not locked");
    }

    /* tstate is allowed to be NULL (early interpreter init) */
    if (tstate != NULL) {
        /* Sub-interpreter support: threads might have been switched
           under our feet using PyThreadState_Swap(). Fix the GIL last
           holder variable so that our heuristics work. */
        _Py_atomic_store_relaxed(&gil->last_holder, (uintptr_t)tstate);
    }

    MUTEX_LOCK(gil->mutex);
    _Py_ANNOTATE_RWLOCK_RELEASED(&gil->locked, /*is_write=*/1);
    _Py_atomic_store_relaxed(&gil->locked, 0);
    COND_SIGNAL(gil->cond);
    MUTEX_UNLOCK(gil->mutex);

#ifdef FORCE_SWITCHING
    if (_Py_atomic_load_relaxed(&ceval2->gil_drop_request) && tstate != NULL) {
        MUTEX_LOCK(gil->switch_mutex);
        /* Not switched yet => wait */
        if (((PyThreadState*)_Py_atomic_load_relaxed(&gil->last_holder)) == tstate)
        {
            assert(_PyThreadState_CheckConsistency(tstate));
            RESET_GIL_DROP_REQUEST(tstate->interp);
            /* NOTE: if COND_WAIT does not atomically start waiting when
               releasing the mutex, another thread can run through, take
               the GIL and drop it again, and reset the condition
               before we even had a chance to wait for it. */
            COND_WAIT(gil->switch_cond, gil->switch_mutex);
        }
        MUTEX_UNLOCK(gil->switch_mutex);
    }
#endif
}
```