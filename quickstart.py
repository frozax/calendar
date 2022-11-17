from __future__ import print_function

import datetime
from dateutil.relativedelta import relativedelta
from dateutil import tz
import time
import calendar
import os.path
import colorama

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/calendar.events"]
service = None

KT_EVENT_NAME = "KT"

def _dt_to_str(dt):
    return dt.isoformat()

class Times:
    def __init__(self, name, time_list):
        self._name = name
        self._time_list = time_list

    def add_to_calendar(self, y, m, d):
        for tstart, tend in self._time_list:
            sminute, ssecond = int(tstart), int((tstart - int(tstart)) * 60)
            eminute, esecond = int(tend), int((tend - int(tend)) * 60)
            start = datetime.datetime(y, m, d, sminute, ssecond, tzinfo=tz.tzlocal())
            end = datetime.datetime(y, m, d, eminute, esecond, tzinfo=tz.tzlocal())
            body = {
                "summary": KT_EVENT_NAME,
                "transparency": "transparent",
                "start": {"dateTime": _dt_to_str(start)},
                "end": {"dateTime": _dt_to_str(end)}
            }
            events_result = service.events().insert(calendarId='primary',
                                                    body=body).execute()
            print(events_result.get("status", "ERROR"))


classic = Times("classic", [(9.5, 12.5), (14, 18)])
tuesday_odd = Times("tuesday_odd", [(9, 12.5), (13.25, 15.25), (15.75, 17.25)])
off = Times("off", [])

YEAR = datetime.datetime.now().year
MONTH = datetime.datetime.now().month
NB_MONTHS = 6

class ColoredTextCalendar(calendar.TextCalendar):

    def formatmonth(self, kt_cal):
        self._kt_cal = kt_cal
        return super().formatmonth(kt_cal._year, kt_cal._month)

    def formatday(self, day, weekday, width):
        times = self._kt_cal._times.get(day, None)
        if times is None or times == off or day == 0:
            cs = colorama.Style.DIM if weekday not in [5, 6] else colorama.Fore.BLACK
        elif times == classic:
            cs = colorama.Fore.LIGHTBLUE_EX
        elif times == tuesday_odd:
            cs = colorama.Fore.YELLOW
        else:
            cs = colorama.Fore.RED
        now = datetime.datetime.today()
        if self._kt_cal._month == now.month and day == now.day:
            cs += colorama.Back.LIGHTWHITE_EX
        return cs + super().formatday(day, weekday, width) + colorama.Style.RESET_ALL

def _str_to_day_hour(s):
    dt = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    return dt.day, dt.hour + dt.minute / 60

class KTCal:
    def __init__(self, theyear, themonth):
        self._year = theyear
        self._month = themonth
        # indexed by day number
        self._times = {}
        # lsit of events to remove them easily
        self._events = {}
        this_month = datetime.datetime(self._year, self._month, day=1, tzinfo=tz.UTC)
        next_month = this_month + relativedelta(months=1)
        events_result = service.events().list(calendarId='primary',
                                              timeMin=_dt_to_str(this_month),
                                              timeMax=_dt_to_str(next_month),
                                              singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        for event in events:
            if event["summary"] == KT_EVENT_NAME:
                ds, hs = _str_to_day_hour(event["start"]["dateTime"])
                de, he = _str_to_day_hour(event["end"]["dateTime"])
                assert ds == de, f"incoherent date {event}"
                assert he > hs, f"incoherent times {event}"
                if ds not in self._times:
                    self._times[ds] = []
                    self._events[ds] = []
                self._times[ds].append((hs, he))
                self._events[ds].append(event["id"])
        for k, v in self._times.items():
            found = False
            for base_times in [classic, tuesday_odd, off]:
                if v == base_times._time_list:
                    self._times[k] = base_times
                    found = True
                    break
            if not found:
                self._times[k] = Times("custom", v)
        

def show_calendar():

    tc = ColoredTextCalendar(0)
    strs = []
    line_width = 20
    for month in range(0, NB_MONTHS):
        dt = datetime.datetime.now() + relativedelta(months=month)
        y, m = dt.year, dt.month
        kt_cal = KTCal(y, m)
        for iline, line in enumerate(tc.formatmonth(kt_cal).splitlines()):
            line = line if len(line) >= 20 else (line + " " * (line_width - len(line)))
            if len(strs) < iline + 1:
                strs.append(line)
            else:
                strs[iline] += (" " * 4) + line
        if month == NB_MONTHS // 2 - 1 or month == NB_MONTHS - 1:
            # print and new line
            for l in strs:
                print(l)
            print()
            strs.clear()

def input_date_to_change():
    input_date = input("Enter date to change (27/7), it will automatically set the proper times and remove if already existing (Use 27/7/s for a special times) :")
    date_split = input_date.split("/")
    if len(date_split) == 2:
        d, m = date_split
        times_to_set = classic
    else:
        d, m, _ = date_split
        times_to_set = tuesday_odd
    m = int(m)
    d = int(d)
    y = YEAR
    # next year support
    if m < MONTH:
        y+=1
    kt_cal = KTCal(y, m)
    existing = kt_cal._times.get(d, off)
    print(f"{d}/{m}/{y}: ", end="")
    if existing == off:
        print(f"nothing, will create a {times_to_set._name} day")
        times_to_set.add_to_calendar(y, m, d)
    else:
        print(f"already a {existing._name}, remove it")
        for event_id in kt_cal._events.get(d, []):
            res = service.events().delete(calendarId="primary", eventId=event_id).execute()


def main():
    while True:
        show_calendar()
        input_date_to_change()
    return


def login():
    global service
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)



def _sample():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    print('Getting the upcoming 10 events')
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                            maxResults=10, singleEvents=True,
                                            orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        print('No upcoming events found.')
        return

    # Prints the start and name of the next 10 events
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(start, event['summary'])


if __name__ == '__main__':
    login()
    try:
        main()
    except HttpError as error:
        print('An error occurred: %s' % error)
