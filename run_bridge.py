import sys
import os

# Import endpoints before starting
import api_system
import api_fs
import api_ui
import api_memory
import api_input
import api_network
import api_chrome
from server import start_server

if __name__ == "__main__":
    start_server()
