import datetime
import os
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler import events
import atexit
import signal
import psutil
import time
import configparser
import sys
import argparse


class bbc_player(object):
	def __init__(self):
		self.read_arguments()
		print('reading configuration from file...')
		config = configparser.ConfigParser()
		config.read(self.config_file)
		for key in config['playback']:
			print(key+':', config['playback'].get(key))
		settings = config['playback']
		print('...configuration read successfully')
		logfile = open(settings.get('log_folder')+'player.log', 'a',1)
		self.time_shift=datetime.timedelta(hours=int(settings.get('time_shift','8')))
		self.output_folder=settings.get('output_folder', '~/')
		playback_begins_string=settings.get('playback_begins','06:00:00')
		playback_ends_string=settings.get('playback_ends','20:00:00')
		self.ffprobe_path=settings.get('ffprobe_path','ffprobe')
		self.vlc_path=settings.get('vlc_path','vlc')
		self.mplayer_path=settings.get('mplayer_path','mplayer')
		self.playback_begins=datetime.datetime.strptime(playback_begins_string, '%H:%M:%S').time()
		self.playback_ends=datetime.datetime.strptime(playback_ends_string,'%H:%M:%S').time()
		# Initialize global variables
		self.running_processes = []
		self.scheduler=BackgroundScheduler()
		self.tracked_files = []
		# Enable debug mode
		if self.debug == True:
			print('debug mode enabled')
			self.time_shift=datetime.timedelta(minutes=2)
			self.playback_begins= datetime.time(00,00,00,0)
			self.playback_ends= datetime.time(23,59,59,0)
		else:
			sys.stdout = logfile
			sys.stderr = logfile
		atexit.register(self.terminate_all)
		self.scheduler.start()
		self.scheduler.add_listener(self.job_listener, events.EVENT_JOB_EXECUTED | events.EVENT_JOB_MISSED | events.EVENT_JOB_ERROR)

	def read_arguments(self):
		parser = argparse.ArgumentParser()

		parser.add_argument(
							"-c","--config_file",
							dest='config_file',
							help='config file',
							required=True
						)
		parser.add_argument(
							"-d", "--debug",
							default=False,
							action='store_true',
							help='run in debug mode'
							)
		args = parser.parse_args()
		if args.debug:
			self.debug = True
		else:
			self.debug = False
		self.config_file = args.config_file

	"""Check length of an arbitrary recording"""
	def get_recording_length(self,file):
		process=self.ffprobe_path+" -show_entries format=Duration -v error "+self.output_folder+file+" | grep 'duration'"
		try:
			duration=float(subprocess.check_output(process, shell=True)[9:].strip())
		except subprocess.CalledProcessError: #If ffprobe is called right when the file is starting to record, it gives an error - need to wait for a duration
			time.sleep(10)
			try:
				duration=float(subprocess.check_output(process, shell=True)[9:].strip())
			except:
				print('problem finding length of file, returning 12 hours')
				duration = 12*60*60#print 'recording', file, 'is', duration, 'seconds long'
		#print(duration, 'for file:', file)
		return duration

	"""Look for new files in the recording folder and add them to scheduler"""
	def poll_files(self):
		for filename in os.listdir(self.output_folder):
			if filename[-4:]=='.mp4':
				recording_start_time=datetime.datetime.strptime(filename, "%Y-%j-%H-%M-%S.mp4")
				ok_to_delete_time=recording_start_time+datetime.timedelta(days=1)
				playback_start_time=recording_start_time+self.time_shift
				#Check for old files and delete them.  Do this approximately because getting precise file length is unreliable from ffprobe.
				if ok_to_delete_time <= datetime.datetime.now():
					print(filename, ' is old - deleting')
					os.remove(self.output_folder+filename)
					try:  #at startup, old files will be deleted, but not have already been tracked - avoid error when trying to delete untracked file.
						self.tracked_files.remove(filename)
					except ValueError:
						continue
				#If the file is supposed to play in the future, schedule it.
				elif playback_start_time > datetime.datetime.now() and filename not in self.tracked_files:
					print(filename, ' is in the future - scheduling playback')
					self.schedule_playback(self.output_folder+filename, playback_start_time)
					self.tracked_files.append(filename)
				#If the file should have already started playing, start playing it now at the appropriate timepoint.
				elif filename not in self.tracked_files:
					start_offset = datetime.datetime.now()- playback_start_time
					if start_offset.total_seconds() < self.get_recording_length(filename):
						print(filename+': attempting playback starting at', start_offset)
						self.start_playback(self.output_folder+filename,start_offset.total_seconds())
					else:
						print(filename+': is in the past')
					self.tracked_files.append(filename)
		if len(self.tracked_files)==0:
				print('scheduler complete - no files scheduled for playback')

	"""Schedule a given filee for a given playback time"""
	def schedule_playback(self,file,start_time):
		print('scheduling playback for', file, 'at', start_time, 'start time is', start_time, 'delay time is', start_time-datetime.datetime.now())
		job = self.scheduler.add_job(self.start_playback,'date',run_date=start_time, args=(file,0))

	"""Start playback partway through a file"""
	def start_playback(self,file,seek_time):
		#command_args = [self.vlc_path, file, '--start-time', str(seek_time), '--play-and-exit','--quiet']
		command_args = [self.mplayer_path,'-quiet','-nolirc','-noar','-nojoystick', '-ss', str(seek_time), file]
		#print(command_args)
		playback_process = subprocess.Popen(command_args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		print('starting playback for', file, 'at', seek_time,'seconds in as pid',playback_process.pid)
		self.running_processes.append(playback_process)

	def terminate_all(self):
		#terminate running processes
		for process in self.running_processes:
			self.end_process(process)

	def end_process(self,subprocess, signal=signal.SIGINT):
		print('ending process pid', subprocess.pid)
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

	def monitor_playback(self):
		while True:
			self.poll_files()  #Check for any newly added files and schedule them.
			#Check status of all running recording processes to make sure that any completed ones end.
			for process in self.running_processes:
				status = process.poll()
				if status == 0:
					self.running_processes.remove(process)
					print(process.pid, 'has completed at',datetime.datetime.now())
					stderr_output = process.stderr.read().splitlines()
					print(f'Error Messages From PID {process.pid}:')
					for line in stderr_output:
						print(str(line))
					if self.debug== True:
						print(f'Output from PID {process.pid}:')
						stdout_output = process.stdout.read().splitlines()
						for line in stdout_output:
							print(str(line))
				else:
					if self.debug == True:
						print(process.pid, 'is still running')

			time.sleep(30)

	def job_listener(self,event):
	    print(event)




if __name__=="__main__":
	    bbc_player().monitor_playback()
