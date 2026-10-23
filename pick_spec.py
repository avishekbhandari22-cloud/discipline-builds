#!/usr/bin/env python3
"""Pick today's spec: day N = days since START_DATE (2026-10-24 -> day 2 ... ). Prints path or nothing if out of specs."""
import datetime, glob, os, re
START = datetime.date(2026, 10, 24)   # day 2 is posted on this date (day 1 was posted manually on 2026-10-23)
today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4 if os.environ.get("EDT","1")=="1" else -5))).date()
n = (today - START).days + 2
p = f"day{n}.json"
print(p if os.path.exists(p) else "")
