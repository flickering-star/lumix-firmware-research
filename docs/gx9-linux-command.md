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

These are ELF virtual addresses, not established USB service addresses for
the live process.

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

The proposed reversible RAM-padding write test was interrupted before any
write was sent. No GX9 RAM writer, live shell, firmware key or alternate firmware
installation has been demonstrated. No firmware update or camera write was
performed during the findings documented here.
