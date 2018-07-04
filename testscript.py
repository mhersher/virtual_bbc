from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import time

scheduler=BackgroundScheduler()

def hello_world():
	print 'hello world'

exec_time = datetime.datetime.now()+datetime.timedelta(minutes=1)
job = scheduler.add_job(hello_world,'date',run_date=exec_time, args=())
#job = scheduler.add_job(hello_world,'interval',seconds=10, args=())
scheduler.start()
time.sleep(75)