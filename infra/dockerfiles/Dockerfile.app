# start from base
FROM python:3.11

LABEL maintainer="voelkerb voelkerb@me.com"

# Set environment variables
ENV PYTHONUNBUFFERED=TRUE
# Port of API
EXPOSE 8000

WORKDIR /usr/src/app

# Avoids installing dependencies if the requirements file has not changed
RUN python -m pip install --upgrade pip
#RUN pip install --upgrade pip setuptools wheel
ADD requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy remaining files
COPY . .

# Show environmental vrriables after build
RUN env


#RUN groupadd -r django && \
#    useradd -r -g django django
#RUN chown -R django:django /usr/src/app
#RUN mkdir /home/django
#USER django
#RUN chown -R django:django /usr/src/app

WORKDIR /usr/src/app
RUN ls -a
RUN python3 manage.py migrate
CMD ["python3", "manage.py", "runsslserver", "0.0.0.0:8000", "--noreload", "--key", "/usr/src/certs/voelkerb_com.key", "--certificate", "/usr/src/certs/voelkerb_com.pem"]