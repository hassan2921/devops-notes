#!/bin/bash
# Task 2: Linux administration demo. Run on the EC2 instance:  bash linux_admin.sh
# (Better: type these one by one during the demo so the examiner sees each.)

echo "== System info =="
whoami                     # current user
hostname                   # machine name
uname -a                   # kernel / OS
uptime                     # load + uptime
df -h                      # disk usage
free -h                    # memory

echo "== Directory work =="
mkdir -p ~/devops-lab/{logs,configs,backups}   # create directories
cd ~/devops-lab
pwd
touch configs/app.conf logs/app.log
echo "APP_ENV=production" > configs/app.conf
ls -la configs logs

echo "== File permissions =="
chmod 600 configs/app.conf      # rw------- : only owner can read/write (secrets)
chmod 644 logs/app.log          # rw-r--r-- : owner writes, others read
chmod 755 backups               # rwxr-xr-x : directory others can enter/list
ls -l configs/app.conf logs/app.log
ls -ld backups

echo "== Ownership =="
sudo chown root:root backups && ls -ld backups
sudo chown "$USER":"$USER" backups && ls -ld backups

echo "== Search / processes / services =="
grep -r "APP_ENV" configs
ps aux | grep -E "docker|gunicorn" | grep -v grep
systemctl status docker --no-pager | head -5
