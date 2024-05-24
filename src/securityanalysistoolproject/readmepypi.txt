change setup.py with new version
python3 setup.py build bdist_wheel
#pip install twine
#for local installs of wheel file
#%pip install dbl-sat-sdk=={SDK_VERSION} --find-links /dbfs/FileStore/tables/dbl_sat_sdk-0.1.14.1-py3-none-any.whl
twine upload dist/dbl_sat_sdk-x.x.x-py3-none-any.whl 
userid is __token__
pwd is <token>

------
https://pypi.org/help/#file-name-reuse 