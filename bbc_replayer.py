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

#Set Global Options
ffmpeg_path = 'ffmpeg'
output_folder = '/home/mhersher/bbc/recordings/'
time_shift = datetime.timedelta(hours=8)
playback_begins = datetime.time(6,0,0,0)  #To economize on data usage, only record and play back during hours that are likely to be listened to.
playback_ends = datetime.time(21,0,0,0)

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
	output_file = output_folder + start_time.strftime("%Y-%j-%H-%M-%S")+'.mp4'
	#schedule_playback(output_file, start_time)
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
		print 'recording process still running'
		time.sleep(1)
		total_file_length=total_file_length+15
		#kill and restart recording every twelve hours to break up recordings to a reasonable length
		if total_file_length >= 43200:
			print 'starting new recording file'
			recording_process.terminate()
			start_recording()
		wait_time = check_recording_hours()
		if wait_time.total_seconds()>0:
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
		recording_ends_today = playback_ends_today - time_shift #determine what datetime today we'll no longer be using today's recordings
		if datetime.datetime.now()>recording_ends_today:
			next_start_playback = datetime.datetime.combine(datetime.date.today()+datetime.timedelta(days=1), playback_begins) #playback should next begin tomorrow at the start time
			next_start_recording = next_start_playback - time_shift # recording should next begin timedelta before tomorrow's playback start time
			wait_time = next_start_recording - datetime.datetime.now() #determine number of seconds until recording should begin again
			print 'recording will restart at ', next_start_recording, 'in ', wait_time, ' seconds'
			return wait_time.total_seconds()
		return 0

#Schedule playback to begin on the appropriate time delay
def schedule_playback(output_file, recording_start_time):
	playback_time=recording_start_time + time_shift
	print 'scheduling playback of', output_file,' for ', playback_time
	playback_command = 'mplayer ' + output_file
	scheduled_playback = s.enterabs(playback_time,1, subprocess.Popen(playback_command, shell=True),0)


#Start up, avoiding 8 hour playback delay if possible.
def startup_scheduler():
	print 'running startup scheduler on ',output_folder
	for filename in os.listdir(output_folder):
		print 'evaluating', filename
		start_time=datetime.datetime.strptime(filename, "%Y-%j-%H-%M-%S.mp4")
		duration=datetime.timedelta(seconds=get_recording_length(output_folder+filename))
		end_time=start_time + duration
		#If the end of the file is before the last time that would still play in the future, delete it.
		if end_time+time_shift <= datetime.datetime.now():
			print filename, ' is old - deleting'
			os.remove(output_folder+filename)
		#If the file is supposed to play in the future, schedule it.
		elif start_time+time_shift > datetime.datetime.now():
			print filename, ' is in the future - scheduling playback'
			output_file = output_folder + filename
			#schedule_playback(output_file, start_time)
		#If the file should have already started playing, start playing it now at the appropriate timepoint.
		else:
			start_offset = datetime.datetime.now()- start_time
			print filename, ' is active now - starting playback with offset ', start_offset
			#subprocess.Popen('mplayer -ss ' + start_offset.seconds + output_folder + filename)
	print 'startup scheduler complete'

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

def get_recording_length(file):
	duration=subprocess.call("ffmpeg -i file 2>&1 | grep 'Duration'| cut -d ' ' -f 4 | sed s/,// | sed 's@\..*@@g' | awk '{ split($1, A, ':'); split(A[3], B, '.'); print 3600*A[1] + 60*A[2] + B[1] }'", shell=True)
	return duration

def terminate():
	#terminate running processes
	for process in running_processes:
		end_process(process)

def end_process(subprocess, signal=signal.SIGTERM):
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
startup_scheduler()
start_recording()