# Scheduling the scout (every 6 hours)

The laptop must be **on and awake** at the scheduled times. A missed run is
harmless: the email is stateless, so the next run just catches up.

The easiest option on any OS is the built-in helper:

```bash
python setup.py install-scheduler       # macOS / Linux / Windows
```

It substitutes the correct project path and registers the schedule for you.

Manual instructions (if you'd rather do it yourself) follow.

---

## macOS (launchd)

1. Get the project's absolute path:
   ```bash
   cd job-scout && pwd
   ```
2. In `scheduler/com.jobscout.plist`, replace **every** `__PROJECT_DIR__` with that path.
3. Make the runner executable and install the agent:
   ```bash
   chmod +x scheduler/run.sh
   cp scheduler/com.jobscout.plist ~/Library/LaunchAgents/com.jobscout.plist
   launchctl load ~/Library/LaunchAgents/com.jobscout.plist
   ```
4. Test immediately:
   ```bash
   launchctl start com.jobscout
   tail -f state/scout.log
   ```
5. To stop/remove:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.jobscout.plist
   ```

Runs at 00:20, 06:20, 12:20, 18:20 local time. Edit the `StartCalendarInterval`
block to change times.

---

## Windows (Task Scheduler)

1. Open a **Command Prompt** in the project folder and create the task:
   ```bat
   schtasks /create /tn "JobScout" /tr "%CD%\scheduler\run.bat" /sc HOURLY /mo 6 /st 00:20
   ```
   `/mo 6` = every 6 hours, starting 00:20.
2. Tell Windows to catch up missed runs (recommended):
   - Task Scheduler → JobScout → Settings → tick **"Run task as soon as possible after a scheduled start is missed"**.
3. Test now:
   ```bat
   schtasks /run /tn "JobScout"
   type state\scout.log
   ```
4. To delete later:
   ```bat
   schtasks /delete /tn "JobScout" /f
   ```

---

## Linux (cron)

```bash
chmod +x scheduler/run.sh
crontab -e
# add this line (adjust the path):
20 */6 * * * /home/you/job-scout/scheduler/run.sh
```
