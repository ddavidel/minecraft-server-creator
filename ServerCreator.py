import os
import os.path
conf = os.path.isfile("config.ini")
if(conf):
    os.system("call main.exe")
else:
    os.system("pip install wget")
    os.system("echo configured>config.ini")
    import wget
    url = "http://mcscreator.altervista.org/releases/latest/main.exe"
    wget.download(url)
    os.system("call main.exe")