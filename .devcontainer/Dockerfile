FROM python:3.10-slim


# Set the default workspace directory (matches devcontainer.json)
# WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install jupyter
# RUN pip install -r requirements.txt 
#--force-reinstall --no-deps
