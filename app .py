from flask import Flask, render_template, request
import subprocess
import threading
import os
import signal

app = Flask(__name__)

# Global variable to keep track of the process
client_process = None

# Speed test function
def iperf_speed_test():
    result = subprocess.run(["iperf3", "-s", "-p", "25001"], capture_output=True, text=True)
    return result.stdout

# Function to start the client main program
def start_client_program():
    global client_process
    client_process = subprocess.Popen(["sudo", "/home/mo/myvenv/bin/python", "base8.py"])

# Function to stop the client main program
def stop_client_program():
    global client_process
    if client_process:
        os.kill(client_process.pid, signal.SIGTERM)
        client_process = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_speed_test', methods=['POST'])
def start_speed_test():
    # Run the speed test function
    speed_test_result = iperf_speed_test()
    return render_template('index.html', speed_test_result=speed_test_result)

@app.route('/start_client_program', methods=['POST'])
def run_client_program():
    # Start the client main program
    threading.Thread(target=start_client_program).start()
    return render_template('index.html', message="Base started successfully!")

@app.route('/halt_client_program', methods=['POST'])
def halt_client_program():
    # Stop the client main program
    stop_client_program()
    return render_template('index.html', message="Base stopped successfully!")

if __name__ == '__main__':
    app.run(debug=True)
