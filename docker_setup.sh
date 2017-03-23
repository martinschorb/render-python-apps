docker pull atbigdawg:5000/fcollman/render-python
docker tag atbigdawg:5000/fcollman/render-python fcollman/render-python
docker build -t fcollman/render-python-apps .
docker tag fcollman/render-python-apps atbigdawg:5000/fcollman/render-python-apps
docker push atbigdawg:5000/fcollman/render-python-apps
docker kill renderapps
docker rm renderapps
docker run -d --name renderapps \
-v /nas:/nas \
-v /nas2:/nas2 \
-v /nas3:/nas3 \
-v /nas4:/nas4 \
-v /data:/data \
-v /pipeline:/pipeline \
-v /pipeline/render-python-apps:/usr/local/render-python-apps \
-v /etc/hosts:/etc/hosts \
-p 8888:8888 \
-e "PASSWORD=$JUPYTERPASSWORD" \
-i -t fcollman/render-python-apps \
/bin/bash -c "/opt/conda/bin/jupyter notebook --config=/root/.jupyter/jupyter_notebook_config.py --notebook-dir=/pipeline/render-python-apps --no-browser" 
 

