#/bin/bash

folder="sat_setup"

pip install -r $folder/requirements.txt
cd $folder
python main.py