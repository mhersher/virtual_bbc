recorder_command="python bbc_recorder.py"
player_command="python bbc_player.py"
nohup $recorder_command &
recorder_pid=$!
nohup $player_command &
player_pid=$!

trap "kill -2 $recorder_pid" 2 15

wait $bg_pid
 