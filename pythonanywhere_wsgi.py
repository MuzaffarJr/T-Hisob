import sys
import os

path = '/home/MuzaffarJr/T-Hisob'
if path not in sys.path:
    sys.path.append(path)

os.chdir(path)
os.environ.setdefault('DATABASE_URL', 'sqlite:////home/MuzaffarJr/T-Hisob/t_hisob.db')
os.environ.setdefault('WEB_APP_URL', 'https://MuzaffarJr.pythonanywhere.com')

from main import app as application
