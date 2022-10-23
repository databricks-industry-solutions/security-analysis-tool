change setup.py with new version
python3 setup.py build bdist_wheel
#pip install twine
twine upload dist/dbl_sat_sdk-x.x.x-py3-none-any.whl 

------
https://pypi.org/help/#file-name-reuse 