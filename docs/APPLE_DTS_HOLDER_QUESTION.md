# Apple technical support question

Status: **not sent.** Do not submit this, and do not open a Feedback Assistant or DTS request, until Yahor authorizes that send. Nothing in this file installs a daemon or changes an entitlement.

## Question

RunSpecimen is a sandboxed Mac App Store app, bundle id `com.darashkevich.runspecimen`, Team ID `UN6KF8636A`. We want another process running as the same user to be unable to rewrite enrollment, the selected approval policy, consumed nonces, and the execution lease. The bounded command itself has to run as that console user, not as root.

Guideline 2.4.5(v), at <https://developer.apple.com/app-store/review/guidelines/>, says Mac App Store apps "may not request escalation to root privileges or use setuid attributes."

Does an embedded `SMAppService.daemon`, which launchd runs as root, violate 2.4.5(v) even when the user approves the background item in System Settings, and even when the daemon's privileged acts are limited to owning a mode `0700` directory and spawning the payload with `setuid` to the console user?

If that is not permitted on the Mac App Store, is a separately distributed Developer ID product the supported place for that daemon, with the Mac App Store app left unable to provide the same-user guarantee?

We have not implemented this daemon and we have not submitted it.
