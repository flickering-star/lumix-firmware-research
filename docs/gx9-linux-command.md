# GX9 internal Linux command handler

The recovered Panasonic `/usr/pvc/bin/psm` executable contains an internal
command runner. Event **`0x3c` / decimal 60**, named **`NET_EVT_LINUX_CMD`**, reaches
`PsmEvt_ElcTestFunction`, which creates a thread that passes a command string to
the imported libc `system` function. The worker can return command output in
event messages. This is a concrete internal command-execution path; an external
USB or Wi-Fi route into it has **not** been demonstrated.

The executable was extracted from the complete recovered second filesystem.
It is 407,276 bytes, SHA-256
`7cafa9b91050c613b9fa76391f12003cbdd0a8e91f4e2e46dc0b22b1a5166fbd`.
The [component report](gx9-recovered-components.md) establishes that the
filesystem contents match the corresponding official GX9 1.5 component after
verified padding reconstruction. The camera owner reports firmware 1.4.

## Native path

| Recovered ELF virtual address | Observed role |
| --- | --- |
| `0x2aa68` | Event-name lookup compares the event with `0x3c` |
| `0x2b294` | Matching case returns the `NET_EVT_LINUX_CMD` string |
| `0x39e94` | Entry of the ELC test-event dispatcher |
| `0x39eb0` | Dispatcher tests event `0x3c` |
| `0x39fdc` | Loads worker address `0x398d8` for `pthread_create` |
| `0x398d8` | Command-worker entry |
| `0x39998`, `0x399dc` | Calls to the imported libc `system` function |

The observed internal message is **488 bytes**. Its event ID is a little-endian
32-bit value at offset zero; the command string begins at offset **24**.
The worker's output length field is at offset **20**. These fields describe an
internal event, not a USB request format or a known network endpoint.

For a command without a `>` character, the worker builds a temporary output
filename from the command's basename. For example, the offline control
`printf GX9_CONSOLE_OK` becomes `printf GX9_CONSOLE_OK > /tmp/printf`. It reads
that file in chunks of at most **175 bytes**, sends output messages of type
**2**, and finally sends CRLF. The dispatcher sends a type-**1** acknowledgement.
A command already containing `>` takes a direct `system` branch without the
same output-return loop. No command from these controls was executed on the
camera or on the host.

## Offline verification

[The verifier](../tools/gx9_linux_command_verify.py) runs the captured native
ARM dispatcher and worker in Unicorn **2.1.4**, using a pinned executable hash.
Libc process/file operations and the two internal IPC helpers are mocked.
There is no host shell invocation, device access or network access.

Four controls pass:

- A short simulated command output returns the marker and CRLF.
- A 400-byte simulated output returns chunks of 175, 175 and 50 bytes, then CRLF.
- The redirection branch passes the expected string to the mocked `system` call.
- The dispatcher copies the 488-byte request and creates the expected worker
  thread with the command intact.

The verifier also checks native event-name comparisons, worker-pointer loads,
call instructions and ELF dynamic relocation names. The
[recorded evidence](../evidence/gx9-linux-command.json) includes input/tool hashes,
message headers and control results.

## Internal event delivery

The recovered `nwa` executable receives an event through the interprocessor
communication (ICC) interface, obtains its shared-memory payload and forwards
the 488-byte message to subscribed local Unix sockets. `psm` connects to
`/tmp/unix_sockstream_nwa` and selects filter row **1**. That row enables event
group zero, which includes event `0x3c`. NWA chooses the filter group by
shifting the event ID right by 12 bits.

The native PSM socket receiver then calls its general event dispatcher, which
routes event IDs 58 through 60 to the ELC dispatcher. The command case remains
event 60. The following path is now checked in native ARM emulation:

```mermaid
flowchart LR
    A[ICC event and shared memory] --> B[nwa subscription filter]
    B --> C[Local Unix socket]
    C --> D[psm socket receiver]
    D --> E[General event dispatcher]
    E --> F[ELC dispatcher: event 60]
```

| ELF virtual address | Verified role |
| --- | --- |
| `nwa:0x111bc` | ICC receive and shared-memory forwarding loop |
| `nwa:0x112ec` | Reads the recipient's filter byte for `event >> 12` |
| `psm:0x72194` | Connection record for the NWA local socket |
| `psm:0x4e93c` | Connects the client and selects its subscription |
| `psm:0x4f598` | Sends the selected 18-byte filter row |
| `psm:0x4e80c` | Receives a message on a ready socket |
| `psm:0x3306c` | General event dispatcher |
| `psm:0x335c0` | Branches to the ELC dispatcher |

These are ELF virtual addresses, with no established translation into USB
service addresses. They are not live camera patch targets.

The [event-path verifier](../tools/gx9_linux_event_path_verify.py) executes the
socket setup, actual filter selection, NWA forwarding, PSM receive and general
dispatch instructions. ICC descriptors, shared memory, sockets, clocks and
diagnostic output are mocked. The supplied message reaches the command
dispatcher unchanged. Clearing the group-zero filter bit suppresses forwarding;
a socket without the readiness flag does not receive or dispatch a message.
The checker stops before thread creation, leaving the command worker to the
separate verifier described above.

The recovered `cam.fcgi` HTTP bridge follows a different initial path. Its
message constructor at `0x11b8c` sets event **`0x6000`**, stores the request's
remote address at offset 16 and decodes the query into offset 184. Native
controls using ordinary queries and a query containing `event=60` all retain
event `0x6000`. A 191-byte unescaped query passes; 192 bytes is rejected. This
checks the wrapper only; downstream query interpretation still needs analysis.

[Event-path evidence](../evidence/gx9-linux-event-path.json) records the pinned
executables, native instruction checks and control results. Reproduce it with:

```sh
python3 tools/gx9_linux_event_path_verify.py \
  --psm work/gx9-filesystems/rootfs2-files/usr/pvc/bin/psm \
  --nwa work/gx9-filesystems/rootfs1-files/usr/pvc/bin/nwa \
  --cgi work/gx9-filesystems/rootfs1-files/etc/www/cam.fcgi \
  --out work/gx9-linux-event-path-check.json
```

Creating an ICC message from an external request remains unresolved. The
emulated event source does not demonstrate USB or Wi-Fi shell access.

With the recovered executable and Unicorn installed:

```sh
python3 tools/gx9_linux_command_verify.py \
  work/gx9-filesystems/rootfs2-files/usr/pvc/bin/psm \
  --out work/gx9-linux-command-check.json
```

## Remaining work

Trace a usable external request path to this internal event. Its presence alone
does not establish that a service-menu toggle, `cam.cgi` request, PTP operation
or USB service command exposes it. Reachability and authentication are unresolved.

The [later ARM-image acquisition recovered the firmware key](gx9-firmware-decryption.md)
and decoded both official update versions completely. That provides the main
camera code needed to continue tracing the event source.

The initially interrupted RAM-padding experiment was later completed: the
[fixed-address `0x9c` write/restore proof](gx9-ram-write.md) verifies a two-byte
change and exact restoration. That does not yet deliver this Linux event or
demonstrate an external shell or modified firmware installation.
