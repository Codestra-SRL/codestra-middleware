# baresip future-run templates

These files are inert preparation artifacts. Do not execute them during
contract review.

The reviewed Ubuntu repository did not offer SIPp or pjsua. The selected
non-GUI client is baresip 1.0.0. The future operator must run it as an
unprivileged account, bind only the approved Server A test address, target only
`10.40.0.2`, enforce one process and one `/dial` command under a 30-second
outer timeout, and store the SIP password in a mode-0600 accounts file outside
the repository. No audio is recorded.

`accounts.example` contains placeholders only. Copy it to a protected runtime
path and replace the placeholder during the separately authorized test. Never
place the password in shell history or command-line arguments.
