# GOLD scraper v2
import mechanize
import re
import getpass
import time
from BeautifulSoup import BeautifulSoup
try:
  from xml.etree import ElementTree
except ImportError:
  from elementtree import ElementTree
import gdata.calendar.data
import gdata.calendar.client
import gdata.acl.data
import sys
import atom


### CLASSES

class Course:
  ''' class Course
        name: The title of the course
        times: An array of Time classes
        final: The time and date of the final as a tuple.  None means no final
        start: first day of class in the format MMDD
        end: last day of class in the format MMDD
  '''
  def __init__(self):
    self.name = ''
    self.times = []
    self.final = None
    self.start = None
    self.end = None
  def __repr__(self):
    return '<Course name:"%s">' % self.name
  def __str__(self):
    return 'Course(name="%s", times=%s)' % (self.name, str(self.times))

class Time:
  ''' class Time
        hours: a tuple of times in python time format.  Might want to change this 
        days: array of days in char format.  The days are Mo Tu We Th Fr
        instructor: name of the instructor as string
        building: name of the building and room number as a string.  Ex: HFH 1202
  '''
  def __init__(self):
    self.hours = (-1, -1)
    self.days = []
    self.instructor = ''
    self.building = ''
  def __repr__(self):
    return '<Time hours:%s days:%s instructor:"%s" building:"%s">' % (self.hours, self.days, self.instructor, self.building)
  def __str__(self):
    return 'Time(hours=%s, days=%s, instructor="%s", building="%s")' % (self.hours, self.days, self.instructor, self.building)
    
    
class GoldUser:
  ''' class GoldUser
        username : username associated with the account
        password : the password of the account
        courses : an array of Courses that the account is taking
  '''
  def __init__(self, username, password):
    self.username = username
    self.password = password
    self.courses = self.__getCourses(username, password)
    
  def __parseTime(self, times):
    ''' function parseTime
          parses a time that it in the format H:MM AM
          note: very fragile
    '''
    x = times.strip().split('-')
    return (time.strptime(x[0], '%I:%M %p'), time.strptime(x[1], '%I:%M %p'))


  def __getCourses(self, username, password):
    ''' function getCourses
          returns an array of Courses'''
    # open the login page and submit with credentials
    br = mechanize.Browser()
    br.open('https://my.sa.ucsb.edu/gold/Login.aspx')
    br.select_form(nr=0)
    br['ctl00$pageContent$userNameText'] = username
    br['ctl00$pageContent$passwordText'] = password
    br['ctl00$pageContent$CredentialCheckBox'] = ['on']
    resp = br.submit()

    if resp.geturl() == 'https://my.sa.ucsb.edu/gold/Login.aspx':
      print 'Invalid username and password'
      return None

    # open courses page
    page = br.open('https://my.sa.ucsb.edu/gold/StudentSchedule.aspx').read()

    # GOLD has an issue...
    page = page.replace('</td></td>', '</td>')
    page = page.replace('&nbsp;',' ')

    # create dom                             
    dom = BeautifulSoup(page)

    # need to get the semester
    semesters = {} # (name, option value, selected)
    for sem in dom.find('select').findAll('option'):
      semesters[sem.string] = (sem['value'], len(sem.attrs) == 2 and sem['selected'] == 'selected')
      
    # promt user to select semester
    for x in semesters:
      print x
    
    usrIn = None
    while not usrIn in semesters:
      usrIn = raw_input("Select a semester: ")
    
    # set start and end times
    startEndDates = {'Fall' : ('0917', '1202'), 'Winter' : ('0109', '0316'), 'Spring' : ('0328', '0603')}
    startDate = usrIn.split(' ')[1] + startEndDates[usrIn.split(' ')[0]][0]
    endDate = usrIn.split(' ')[1] + startEndDates[usrIn.split(' ')[0]][1]

    # if we arent on the right page
    if not semesters[usrIn][1]:
      br.select_form(name='aspnetForm')
      br['ctl00$pageContent$quarterDropDown'] = [semesters[usrIn][0]]
      page = br.submit().read()
      
      # GOLD has an issue...
      page = page.replace('</td></td>', '</td>')
      page = page.replace('&nbsp;',' ')

      # create dom                             
      dom = BeautifulSoup(page)
      

    # loop through each course
    courses = []
    i = 0
    while True:

      # get the class title
      classTitle = dom.find('span', id=re.compile('pageContent_CourseList_CourseHeadingLabel(Alternate)?_'+str(i)))
      if classTitle == None:
        # break the loop if there isn't a class title
        break

      course = Course()
      # handle red names
      coursefield = classTitle.contents[0]
      if coursefield.string.startswith('<'):
        coursefield = coursefield.contents[0]
      course.name = re.sub(r'\s+',' ', coursefield.string)
      course.start = startDate
      course.end = endDate

      # get the instructors as an array
      instructors = []
      for x in dom.find('table', id='pageContent_CourseList_InstructorList_'+str(i)).findAll('table'): # way to get all teacher names
        s = str(x.find('td').contents[0])
        if s != '' and s != ' ':
          instructors.append(s)

      # get the class times
      classTimes = []

      elems = dom.find('table', id='pageContent_CourseList_MeetingTimesList_'+str(i)).findAll('td', {'class': re.compile('clcellprimary(alt)?')})

      for j in range(0,len(elems),3):
        tmp = Time()
        tmp.hours = self.__parseTime(str(elems[j+1].contents[0]))
        for day in str(elems[j].contents[0]).strip().split(' '):
          daysConversion = {'M': 'MO', 'T': 'TU', 'W': 'WE', 'R': 'TH', 'F': 'FR'}
          tmp.days.append(daysConversion[day])
        tmp.building = str(elems[j+2].a.contents[0])
        classTimes.append(tmp)

      for x in range(0,len(instructors)):
        if x == 0:
          classTimes[x].instructor = instructors[x]

      course.times = classTimes
      courses.append(course)
      i += 1

    
    # get final exams
    '''
    finals = dom.find('table', id='ctl00_pageContent_FinalsGrid').findAll('table')
    for j in range(1,len(finals)): # first table is the header
      tds = finals[j].findAll('td', 'clcellprimary') # tds[0] is the course name, tds[1] is the time
      if str(tds[1].contents[0]) != 'Contact Professor for Final Exam Information':
        times = tds[1].contents[0]
        courses[j-1].final = (time.strptime(times.split(' - ')[0], '%A, %B %d, %Y %I:%M %p'), time.strptime(re.sub(r' \d{1,2}:\d{2} (A|P)M - ', ' ', times), '%A, %B %d, %Y %I:%M %p'))
    '''

    return courses


class GCalUser:
  ''' class GCalUser
        client : Used to fetch and creat calendar events
  '''
  def __init__(self, username, password):
    self.client = gdata.calendar.client.CalendarClient(source='GOLD Scraper')
    self.client.ClientLogin(username, password, self.client.source)
    # select a calendar
    self.cal = None
    
    feed = self.client.GetAllCalendarsFeed()
    for i, a_calendar in zip(xrange(len(feed.entry)), feed.entry):
      print '%s. %s' % (i+1, a_calendar.title.text,)

    
    usrIn = None
    while not usrIn in range(0,len(feed.entry)):
      usrIn = int(raw_input("Select a calendar: "))-1
    self.cal = feed.entry[usrIn].content.src
    
    
  def addCourse(self, course):
    
    
    for t in course.times:
      event = gdata.calendar.data.CalendarEventEntry()
      event.title = atom.data.Title(text=course.name.split(' - ')[0])
      event.content = atom.data.Content(text=course.name.split(' - ')[1]+'\nInstructor: %s' % t.instructor)
      event.where.append(gdata.data.Where(value=t.building))
      event.recurrence = gdata.data.Recurrence(text='DTSTART;TZID=America/Los_Angeles:%sT%s\r\n' % (course.start, time.strftime('%H%M%S', t.hours[0]))
        + 'DTEND:%sT%s\r\n' % (course.start, time.strftime('%H%M%S', t.hours[1]))
        + 'RRULE:FREQ=WEEKLY;BYDAY=%s;UNTIL=%s\r\n' % (','.join(t.days), course.end)
        + 'EXDATE:%sT%s\r\n' % (course.start, time.strftime('%H%M%S', t.hours[0]))) # exclude the first date
      new_event = self.client.InsertEvent(event, self.cal)
      
    # add the final
    if course.final != None:
      event = gdata.calendar.data.CalendarEventEntry()
      event.title = atom.data.Title(text=course.name + " Final Exam")
      ## set timezone not working
      event.timezone = gdata.calendar.Timezone(value='America/Los_Angeles')
      start_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', course.final[0])
      end_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', course.final[1])
      event.when.append(gdata.data.When(start=start_time, end=end_time))
      new_event = self.client.InsertEvent(event, self.cal)




### MAIN

print 'Log in to gold'
gusername = raw_input('Username: ')
gpassword = getpass.getpass('Password: ')

print 'Log in to google calendar'
cusername = raw_input('Username: ')
cpassword = getpass.getpass('Password: ')

guser = GoldUser(gusername, gpassword)
cuser = GCalUser(cusername, cpassword)

if guser.courses == None:
  print 'No classes'
  sys.exit(1)

for c in guser.courses:
  print 'Adding ' + c.name
  cuser.addCourse(c)
  

