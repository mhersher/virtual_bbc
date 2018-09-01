import subprocess
import datetime
import sched
import os
import time
import urllib
import atexit
import signal
try:
	import psutil
except ImportError:
	print 'psutil not installed'
	exit()
try:
	import configparser
except ImportError:
	print 'configparser not installed'
	exit()
import sys

#Set Global Options
ffmpeg_path = 'ffmpeg'
#Set Global Options
print 'reading configuration from bbc_replayer.conf'
config = configparser.ConfigParser()
config.read(os.path.dirname(os.path.realpath(sys.argv[0]))+'/bbc_replayer.conf')
settings = config['default']
#Send logs and errors to logfile
logfile = open(settings.get('log_folder')+'player.log', 'a',0)
sys.stdout = logfile
sys.stderr = logfile
time_shift=datetime.timedelta(hours=int(settings.get('time_shift','8')))
output_folder=settings.get('output_folder', '~/')
playback_begins_string=settings.get('playback_begins','06:00:00')
playback_ends_string=settings.get('playback_ends','20:00:00')
playback_begins=datetime.datetime.strptime(playback_begins_string, '%H:%M:%S').time()
playback_ends=datetime.datetime.strptime(playback_ends_string,'%H:%M:%S').time()
debug=False
if settings.getboolean('debug'):
	print 'debug mode enabled'
	debug=True
	time_shift=datetime.timedelta(minutes=2)
	playback_begins= datetime.time(00,00,00,0)
	playback_ends= datetime.time(23,59,59,0)

# Initialize global variables
s = sched.scheduler(time.time, time.sleep)
running_processes = []


def start_recording():
	wait_time = check_recording_hours()
	if wait_time>0:
		time.sleep(wait_time)
	print 'starting recording'
	try:
		check_internet()
	except IOError:
		time.sleep(60)
		start_recording()
	start_time = datetime.datetime.now()
	output_file = output_folder + start_time.strftime("%Y-%j-%H-%M-%S")+'.mp3'
	recording_command = ffmpeg_path + ' -i http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p -codec copy ' + output_file + ' -loglevel warning -hide_banner'
	#start recording process
	recording_process = subprocess.Popen(recording_command, shell=True)
	running_processes.append(recording_process)
	#monitor recording process, and restart it if needed
	time.sleep(5) #wait five seconds to give recording a chance to start before handing off
	manage_recording(recording_process)

def manage_recording(recording_process):
	#watch for unexpected recording process closing and restart the process
	total_file_length = 0
	while recording_process.poll() is None:
		if debug == True:
			print 'recording process still running at', datetime.datetime.now()
		time.sleep(30)
		total_file_length=total_file_length+15
		#kill and restart recording every twelve hours to break up recordings to a reasonable length
		if total_file_length >= 43200:
			print 'starting new recording file'
			recording_process.terminate()
			start_recording()
		wait_time = check_recording_hours()
		if wait_time>0:
			print 'ending process for today'
			end_process(recording_process)
			time.sleep(wait_time)
			print 'restarting recording after overnight break'
			start_recording()
	print 'recording process stopped - restarting'
	#remove process ID from running process list
	running_processes.remove(recording_process)
	start_recording()

def check_recording_hours():
		playback_ends_today = datetime.datetime.combine(datetime.date.today(),playback_ends) #build datetime where playback ends today
		recording_ends_today = playback_ends_today - time_shift + datetime.timedelta(days=1) #determine what datetime today we'll no longer be using today's recordings
		#print playback_ends_today, recording_ends_today
		if datetime.datetime.now()>recording_ends_today:
			next_start_playback = datetime.datetime.combine(datetime.date.today()+datetime.timedelta(days=1), playback_begins) #playback should next begin tomorrow at the start time
			next_start_recording = next_start_playback - time_shift # recording should next begin timedelta before tomorrow's playback start time
			wait_time = next_start_recording - datetime.datetime.now() #determine number of seconds until recording should begin again
			print 'recording will restart at ', next_start_recording, 'in ', wait_time, ' seconds'
			return wait_time.total_seconds()
		return 0

#Get rid of old recordings once the're not needed
def cleanup_recordings():
	for filename in os.listdir(output_folder):
		start_time=datetime.datetime.strptime(filename, "%Y-%j-%H-%M-%S.mp4")
		duration=datetime.timedelta(seconds=recording_length(output_folder+filename))
		end_time=start_time + duration
		#If the end of the file is before the last time that would still play in the future, delete it.
		if end_time+time_shift <= datetime.datetime.now():
			os.remove(output_folder+filename)
	return

def check_internet():
	#check internet connection
	try:
		urllib.urlopen("http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p")
		print 'internet connection confirmed'
	except:
		try:
			urllib.urlopen("http://example.com")
			print "Can't find stream, but internet connection confirmed.  Retrying in 60 seconds"
			return IOError
		except IOError:
			print 'No internet connection.  Retrying in 60 seconds'
			return IOError
	return True

def terminate():
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

atexit.register(terminate)
start_recording()