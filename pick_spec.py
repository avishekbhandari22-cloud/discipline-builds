#!/usr/bin/env python3
# Days 1-7 are already scheduled in YouTube Studio (Oct 23-29). Automation starts at day 8 on 2026-10-30.
import datetime, os
START = datetime.date(2026, 10, 30)
off = -4 if os.environ.get("EDT","1")=="1" else -5
today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=off))).date()
n = (today - START).days + 8
p = "day%d.json" % n
print(p if os.path.exists(p) else "")
