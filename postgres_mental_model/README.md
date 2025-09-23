# A basic mental model of Postgres

## Storage

### Pages
- tables and indices are stored on disk in pages (8KB) which get put into shared memory, edited, then written out

### WAL
- Append only log of all insert, updates, delete, create index, etc.
- Postgres writes changes to the WAL first



## A SELECT query
1. The postmaster process listens for TCP connections from clients.
    - https://github.com/postgres/postgres/blob/a48d1ef58652229521ba4b5070e19f857608b22e/src/backend/postmaster/postmaster.c#L1142
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


6. Client sends a SimpleQuery ('Q') containing some sql 
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

## Background Processes

While Postmaster is listening for TCP connections, a few other processes are running.

src/backend/postmaster/

- WAL Writer 
    - Not an essential process, backends can do everything that this process does
    - Keeps backends from having to fsync WAL pages
- Background writer
    - writes out dirty shared buffers in background in order to mantain enough clean shared buffers. backends will still write to shared buffers if the background writer doesnt keep up
- Checkpointer
- Autovacuum
- WAL sender / WAL receiver
    - replication
- Syslogger
    - logs