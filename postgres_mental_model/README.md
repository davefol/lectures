# A basic mental model of Postgres

## Background
- fsync/FlushFileBuffers: normally when you write to a file, the OS batches the writes so that each little byte doesnt result in hitting the actual disk. fsync forces the writes to actually go to the disk.
- tuple: What postgres calls rows internally, includes metadata https://github.com/postgres/postgres/blob/f2bae51dfd5b2edc460c86071c577a45a1acbfd7/src/include/access/htup.h#L69
- page: a block of virtual memory that the OS hands out to your program. OS keeps track of which process page matches on to actual memory pages. useful for handing out the same page to multiple programs to avoid context switches and for abstracting/protecting virtual memory.
  
## WAL
- The write ahead log is a list of edits to the database.
- It is the core datastructure of PostgreSQL, what makes it unique from other DBs, and the source of truth.
- Postgres writes to the WAL first

## Pages
All data is organized in the form of 8KB pages.

Table and index pages have a short header followed by a series of item ids. 
The item ids point into locations in the same file that contain the items (the actual row data).
At the end there is some reserved bytes used if the page is an index (as opposed to table data) page.
On disk the 8KB pages get batched up into 1GB data files.

WAL pages are a list of operations (insert, update, delete, etc.) 
On disk, the 8 KB pages get batched up into 16MB WAL files.

To modify a page we need to bring it into shared memory. We do this with mmap and semaphores. We call pages in memory that dont match their on disk counterpart "dirty".
This isn't huge ~128 MB of shared memory by default. 

## Query pipeline
1. The postmaster process listens for TCP connections from clients.
    - https://github.com/postgres/postgres/blob/a48d1ef58652229521ba4b5070e19f857608b22e/src/backend/postmaster/postmaster.c#L1142
    - Remeber, applications (layer 7) interact with the transport layer (TCP/UDP layer 4) through the socket API. Most of the TCP stuff is abstracted away in the socket state machine. we can treat the socket as a file descriptor
    - we'll do a lecture on sockets and file descriptors another time
2. A client connects to the postmaster process and the process gets forked. 
    - BackendStartup (keeps track of processes and calls fork() under the hood) https://github.com/postgres/postgres/blob/a48d1ef58652229521ba4b5070e19f857608b22e/src/backend/postmaster/postmaster.c#L1705

    Will call BackendMain

Side note: Postgresql wire format
    - 1 byte for message typ
    - 4 bytes for length of rest of message
    - SQL is sent as plain text
    - Incomplete message results in abandoning the connection

3. Client sends StartupMessage
    - name of user
    - database
    - protocol version

    Server handles this in BackendInitialize (inside BackendMain) which calls
    ProcessStartupPacket


4. Server authenticates client and sends back AuthenticationOk (the byte 'R')

    After BackendInitialize, server call s
    PostgresMain -> InitPostgres -> ClientAuthentication

    - https://github.com/postgres/postgres/blob/a48d1ef58652229521ba4b5070e19f857608b22e/src/backend/libpq/auth.c#L677

5. Client waits for server to finish its startup, expecting ParameterStatus, BackendKeyData ReadyForQuery ('Z' byte for type)

    - https://github.com/postgres/postgres/blob/a48d1ef58652229521ba4b5070e19f857608b22e/src/backend/tcop/dest.c#L267

    - BackendKeyData is a secret key for cancelling requests
    - ParameterStatus are just various info about the server like version and time zone


6. Client sends a SimpleQuery ('Q') containing some SQL (eg SELECT * from some_table)
- https://github.com/postgres/postgres/blob/a48d1ef58652229521ba4b5070e19f857608b22e/src/backend/tcop/postgres.c#L1016

7. The server parses the query
    - pg_parse_query to get the query tree

8. The server rewrites the query
    - pg_analyze_and_rewrite_fixedparams/varparams 

9. The server plans the query
    - pg_plan_queries
    1. Enumerate all possible paths ie scan, use index
    2. Score each path
    3. Pick cheapest path and expand to full plan

10. The server executes the query plan
    1. CreatePortal
    2. PortalDefineQuery
    3. PortalStart

11. Server sends RowDescription ('T')
    - This contains the column names

12. Server sends DataRow
    - This contins the actual data

13. Server sends CommandComplete
    - Marks data as done

14. Server sends another ReadyForQuery to start the cycle all over again

15. Client sends simple query containing some SQL (eg. INSERT INTO some_table COLUMNS (a, b, c) values (1, 2, 3))

16. parse, reweirte, plan

17. Execute, calling ModifyTable
    - find free space in a page
    - write WAL and table/heap page
    - create matching index entries in WAL and index/heap page

18. Client sends commit which gets added to WAL and marks the changes as visible
    - by default, commit gurantees that WAL is fsync'd to disk

## Background Processes

While Postmaster is listening for TCP connections, a few other processes are running.

src/backend/postmaster/

- WAL Writer 
    - Not an essential process, backends can do everything that this process does
    - Keeps backends from having to fsync WAL pages
    - means we will probably fsync before we actually hit a commit but this is fine
- Background writer
    - writes out dirty shared buffers in background in order to mantain enough clean shared buffers, **NOT fsync**. backends will still write to shared buffers if the background writer doesnt keep up
- Checkpointer
    - writes out WAL and pages to disk, **IS fsync**. This creates a checkpoint where we know our state is consistent and actually on disk. If we crash, we start from the latest checkpoint and replay the WAL to rebuild the pages.
- Autovacuum
    - clean out useless tuples. eg an update creates a new tuple so the old one can be tossed out.
- WAL sender / WAL receiver
    - replication
- Syslogger
    - logs
