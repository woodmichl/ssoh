# Sort of STONITH OPNsense Helper (SSOH)
## What is it?
It's basically a Python script that checks if it can ping certain IP addresses.

If enough of the IP addresses are unreachable it sends a ForceRestart command to the Redfish API specified in the config.

## Why is it?
My OPNsense instance was havin strange problems where it would just freeze.
I suspect that it was a faulty SSD that has since been replaced, but I can't say for sure because no log was written at all when the freezes happened.

Since Murphy's Law dictates that these freezes only happened when I was about 400km away from the machine and had to call my not-so-tech-savvy family to flip the power switch, I wanted an automated solution.

## Disclaimer
I'm well aware that this solution is far from being perfect (and even far from being good), but it should help my problem, and that's what it is about.

This solution should also probably not be used in a production environment and I'm not responsible for any damage caused by it. 