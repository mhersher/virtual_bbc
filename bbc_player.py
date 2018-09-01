import datetime
import os
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import signal
import psutil
import time
try:
	import configparser
except ImportError:
	print 'configparser not installed'
	exit()
import sys

#Set Global Options
print 'reading configuration from bbc_replayer.conf'
config = configparser.ConfigParser()
config.read('bbc_replayer.conf')
settings = config['default']
#Send stdout to logfile
sys.stdout = open(settings.get('log_folder')+'player.log', 'a',0)
time_shift=datetime.timedelta(hours=int(settings.get('time_shift','8')))
output_folder=settings.get('output_folder', '~/')
playback_begins_string=settings.get('playback_begins','06:00:00')
playback_ends_string=settings.get('playback_ends','20:00:00')
playback_begins=datetime.datetime.strptime(playback_begins_string, "%H:%M:%S")
playback_ends=datetime.datetime.strptime(playback_ends_string,"%H:%M:%S")
if settings.getboolean('debug'):
	print 'debug mode enabled'
	time_shift=datetime.timedelta(minutes=2)
	playback_begins= datetime.time(00,00,00,0)
	playback_ends= datetime.time(23,59,59,0)

#Global variables
running_processes = []
scheduler=BackgroundScheduler()
tracked_files = []

"""Check length of an arbitrary recording"""
def get_recording_length(file):
	process="ffprobe -show_entries format=Duration -v error "+output_folder+file+" | grep 'duration'"
	try:
		duration=float(subprocess.check_output(process, shell=True)[9:].strip())
	except subprocess.CalledProcessError: #If ffprobe is called right when the file is starting to record, it gives an error - need to wait for a duration
		time.sleep(10)
		duration=float(subprocess.check_output(process, shell=True)[9:].strip())
	#print 'recording', file, 'is', duration, 'seconds long'
	return duration

"""Look for new files in the recording folder and add them to scheduler"""
def poll_files():
	for filename in os.listdir(output_folder):
		duration = datetime.timedelta(seconds=get_recording_length(filename))
		recording_start_time=datetime.datetime.strptime(filename, "%Y-%j-%H-%M-%S.mp3")
		recording_end_time=recording_start_time + duration
		playback_start_time=recording_start_time+time_shift
		playback_end_time=recording_end_time+time_shift
		#If the end of the file is before the last time that would still play in the future, delete it.
		if playback_end_time <= datetime.datetime.now():
			print filename, ' is old - deleting'
			os.remove(output_folder+filename)
			try:  #at startup, old fiiles will be deleted, but not have already been tracked - avoid error when trying to delete untracked file.
				tracked_files.remove(filename)
			except ValueError:
				continue
		#If the file is supposed to play in the future, schedule it.
		elif playback_start_time > datetime.datetime.now() and filename not in tracked_files:
			print filename, ' is in the future - scheduling playback'
			schedule_playback(output_folder+filename, playback_start_time)
			tracked_files.append(filename)
		#If the file should have already started playing, start playing it now at the appropriate timepoint.
		elif filename not in tracked_files:
			start_offset = datetime.datetime.now()- playback_start_time
			print filename, 'is active now - starting playback', start_offset
			start_playback(output_folder+filename,start_offset)
			tracked_files.append(filename)
	if len(tracked_files)==0:
			print 'scheduler complete - no files scheduled for playback'

"""Schedule a given filee for a given playback time"""
def schedule_playback(file,start_time):
	print 'scheduling playback for', file, 'at', start_time, 'start time is', start_time, 'delay time is', start_time-datetime.datetime.now()
	#s.enter(start_time-time.time(),1,start_playback(file,0),())
	job = scheduler.add_job(start_playback,'date',run_date=start_time, args=(file,0))

"""Start playback partway through a file"""
def start_playback(file,seek_time):
	print 'starting playback for', file, 'at', seek_time,'seconds in'
	command = 'mplayer -really-quiet -ss ' + str(seek_time) + ' ' + file
	playback_process = subprocess.Popen(command, shell=True)
	running_processes.append(playback_process)

def terminate_all():
	#terminate running processes
	for process in running_processes:
		end_process(process)

def end_process(subprocess, signal=signal.SIGINT):
	print 'ending process pid', subprocess.pid
	ppid=subprocess.pid
	try:
		process = psutil.Process(ppid)
	except psutil.NoSuchProcess:
		return
	pids = process.children(recursive=True)
	for pid in pids:
		os.kill(pid.pid, signal)
	subprocess.terminate()
	try:
		subprocess.wait()
	except:
		subprocess.kill()

def monitor_playback():
	while True:
		poll_files()  #Check for any newly added files and schedule them.
		time.sleep(30)

atexit.register(terminate_all)
#startup()
scheduler.start()
monitor_playback()