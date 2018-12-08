FROM bboerst/rpi-qemu-alpine-python:3

WORKDIR /usr/src/app

COPY . ./

CMD ["python", "./main.py"]