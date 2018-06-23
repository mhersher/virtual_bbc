import subprocess
import datetime
import sched
import os
import time
import urllib
import atexit

#Set Global Options
ffmpeg_path = 'ffmpeg'
output_folder = '/home/mhersher/bbc/recordings/'
time_shift = datetime.timedelta(hours=8)

# Initialize global variables
s = sched.scheduler(time.time, time.sleep)
running_processes = []

def start_recording():
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
	total_file_length=0
	time.sleep(5) #wait five seconds to give recording a chance to start before handing off
	manage_recording(recording_process)

def manage_recording(recording_process):
	#watch for unexpected recording process closing and restart the process
	while recording_process.poll() is None:
		print 'recording process still running'
		time.sleep(15)
		total_file_length=total_file_length+15
		#kill and restart recording every twelve hours to break up recordings to a reasonable length
		if total_file_length >= 43200:
			print 'starting new recording file'
			recording_process.terminate()
			start_recording()
	print 'recording process stopped - restarting'
	#remove process ID from running process list
	running_processes.remove(recording_process)
	start_recording()


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
		process.terminate()
		try:
			process.wait(10)
		except:
			process.kill()

atexit.register(terminate)
startup_scheduler()
start_recording()