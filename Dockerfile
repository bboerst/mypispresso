FROM hypriot/rpi-alpine

RUN apk add --no-cache linux-headers gcc musl-dev jpeg-dev zlib-dev freetype-dev

WORKDIR /usr/src/app

RUN pip install --no-cache-dir rpi.gpio numpy spidev pillow

COPY . ./

CMD ["python", "./main.py"]
