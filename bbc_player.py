import datetime
import os
import subprocess
import sched
import atexit
import signal
import psutil

#Set Global Options
ffmpeg_path = 'ffmpeg'
output_folder = '/home/mhersher/bbc/recordings/'
time_shift = datetime.timedelta(minutes=8)
playback_begins = datetime.time(5,30,0,0)  #To economize on data usage, only record and play back during hours that are likely to be listened to.
playback_ends = datetime.time(21,0,0,0)


#Global variables
running_processes = []
s = sched.scheduler(time.time, time.sleep)

"""Check length of an arbitrary recording"""
def get_recording_length(file):
	process="ffprobe -show_entries format=Duration -v error "+output_folder+file+" | grep 'duration'"
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
		#If the file is supposed to play in the future, schedule it.
		elif playback_start_time > datetime.datetime.now():
			print filename, ' is in the future - scheduling playback'
			schedule_playback(output_folder+filename, playback_start_time)
		#If the file should have already started playing, start playing it now at the appropriate timepoint.
		else:
			start_offset = datetime.datetime.now()- playback_start_time
			print filename, 'is active now - starting playback', start_offset
			start_playback(output_folder+filename,start_offset)
	print 'startup scheduler complete'

"""Schedule a given filee for a given playback time"""
def schedule_playback(file,start_time):
	print 'stub scheduling playback for', file, 'at', start_time
	return

"""Start playback partway through a file"""
def start_playback(file,seek_time):
	print 'starting playbback for', file, 'at', seek_time,'seconds in'
	command = 'mplayer -really-quiet -ss ' + str(seek_time) + ' ' + file
	playback_process = subprocess.Popen(command, shell=True)
	running_processes.append(playback_process)
	return

"""Review all files on startup and schedule playback"""
def startup():
	poll_files()
	return

def terminate_all():
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

atexit.register(terminate_all)
startup()
s.run()