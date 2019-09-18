import subprocess
import datetime
import sched
import os
import time
import urllib.request
import atexit
import signal
import psutil
import configparser
import sys
import argparse

class bbc_recorder(object):
	def __init__(self):
		self.read_arguments()
		print('reading configuration from file...')
		config = configparser.ConfigParser()
		config.read(self.config_file)
		for key in config['recording']:
			print(key)
		settings = config['recording']
		print('...configuration read successfully')
		logfile = open(settings.get('log_folder')+'recorder.log', 'a')
		self.time_shift=datetime.timedelta(hours=int(settings.get('time_shift','8')))
		self.output_folder=settings.get('output_folder', '~/')
		playback_begins_string=settings.get('playback_begins','06:00:00')
		playback_ends_string=settings.get('playback_ends','20:00:00')
		self.ffmpeg_path=settings.get('ffmpeg_path','ffmpeg')
		self.playback_begins=datetime.datetime.strptime(playback_begins_string, '%H:%M:%S').time()
		self.playback_ends=datetime.datetime.strptime(playback_ends_string,'%H:%M:%S').time()
		# Initialize global variables
		self.s = sched.scheduler(time.time, time.sleep)
		self.running_processes = []
		if self.debug == True:
			print('debug mode enabled')
			time_shift=datetime.timedelta(minutes=2)
			playback_begins= datetime.time(00,00,00,0)
			playback_ends= datetime.time(23,59,59,0)
		else:
			sys.stdout = logfile
			sys.stderr = logfile
		atexit.register(self.terminate)

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

	def start_recording(self):
		print('starting recording')
		try:
			self.check_internet()
		except IOError:
			time.sleep(60)
			self.start_recording()
		start_time = datetime.datetime.now()
		output_file = self.output_folder + start_time.strftime("%Y-%j-%H-%M-%S")+'.mp4'
		#recording_command = ffmpeg_path + ' -i http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p -codec copy ' + output_file + ' -loglevel warning -hide_banner'
		recording_command = self.ffmpeg_path + ' -analyzeduration 20000000 -probesize 20000000 -hide_banner -loglevel warning -re -i http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p -c copy ' + output_file
		#print(recording_command)
		#start recording process
		recording_process = subprocess.Popen(recording_command, shell=True)
		self.running_processes.append(recording_process)
		#monitor recording process, and restart it if needed
		time.sleep(5) #wait five seconds to give recording a chance to start before handing off
		print('recording process started, pid '+str(recording_process.pid))
		self.manage_recording(recording_process)

	def manage_recording(self,recording_process):
		#watch for unexpected recording process closing and restart the process
		total_file_length = 0
		log_timer=0
		while recording_process.poll() is None:
			log_timer += 30
			if self.debug == True and log_timer > 60:
				print('recording process still running at', datetime.datetime.now())
				log_timer=0
				time.sleep(30)
			elif log_timer>300:
				print('recording process still running at', datetime.datetime.now())
				log_timer=0
				time.sleep(30)
		total_file_length=total_file_length+30
		#kill and restart recording every twelve hours to break up recordings to a reasonable length
		if total_file_length >= 43200:
			print('recording process is now '+str(total_file_length/60)+ ' minutes long.  Starting new file')
	        #print 'ending recording process pid '+str(recording_process.pid)
			end_process(recording_process)
			self.start_recording()
		if self.check_recording_hours()==-1:
			print('ending recording process for today')
			self.end_process(recording_process)
			while check_recording_hours()==-1:
				time.sleep(300)
			print('restarting recording after overnight break')
			self.start_recording()
		print('recording process stopped - restarting')
		#remove process ID from running process list
		self.running_processes.remove(recording_process)
		self.start_recording()

	def check_recording_hours(self):
	        current_time = datetime.datetime.now().time()
	        recording_begins = (datetime.datetime.combine(datetime.date.today(), self.playback_begins)-self.time_shift).time()
	        recording_ends = (datetime.datetime.combine(datetime.date.today(), self.playback_ends)-self.time_shift).time()
	        #print 'current time is',current_time,'recording begins at',recording_begins,'recording_ends at',recording_ends
	        if current_time > recording_begins or current_time < recording_ends:
	            return 0
	        else:
	            print('outside of recording hours')
	            print('current time is',current_time,'recording begins at',recording_begins,'recording_ends at',recording_ends)
	            return -1

	#Get rid of old recordings once the're not needed
	def cleanup_recordings(self):
		for filename in os.listdir(output_folder):
			start_time=datetime.datetime.strptime(filename, "%Y-%j-%H-%M-%S.mp4")
			duration=datetime.timedelta(seconds=recording_length(output_folder+filename))
			end_time=start_time + duration
			#If the end of the file is before the last time that would still play in the future, delete it.
			if end_time+time_shift <= datetime.datetime.now():
				os.remove(output_folder+filename)
		return

	def check_internet(self):
		#check internet connection
		try:
			urllib.request.urlopen("http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p")
			print('internet connection confirmed')
		except:
			try:
				urllib.request.urlopen("http://example.com")
				print("Can't find stream, but internet connection confirmed.  Retrying in 60 seconds")
				time.sleep(60)
				return IOError
			except IOError:
				print('No internet connection.  Retrying in 60 seconds')
				time.sleep(60)
				return IOError
		return True

	def terminate(self):
		#terminate running processes
		for process in self.running_processes:
			self.end_process(process)

	def end_process(self, subprocess, signal=signal.SIGINT):
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



if __name__=="__main__":
	    bbc_recorder().start_recording()
