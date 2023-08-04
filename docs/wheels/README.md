## wheels only needed incase internet/pypi access is blocked
## wheel files for SAT offline access

```#%pip install dbl-sat-sdk=={SDK_VERSION}

%pip install cachetools --find-links /dbfs/FileStore/wheels/cachetools-5.3.1-py3-none-any.whl
%pip install pyasn1 --find-links /dbfs/FileStore/wheels/pyasn1-0.5.0-py2.py3-none-any.whl
%pip install pyasn1-modules --find-links /dbfs/FileStore/wheels/pyasn1_modules-0.3.0-py2.py3-none-any.whl
%pip install rsa --find-links /dbfs/FileStore/wheels/rsa-4.9-py3-none-any.whl
%pip install google-auth --find-links /dbfs/FileStore/wheels/google_auth-2.22.0-py2.py3-none-any.whl
%pip install PyJWT[crypto] --find-links /dbfs/FileStore/wheels/PyJWT-2.8.0-py3-none-any.whl
%pip install msal --find-links /dbfs/FileStore/wheels/msal-1.22.0-py2.py3-none-any.whl
%pip install dbl-sat-sdk==0.1.32 --find-links /dbfs/FileStore/wheels/dbl_sat_sdk-0.1.32-py3-none-any.whl```
