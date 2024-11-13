FROM python:3.6
COPY . /app/nhl-twitter-bot
COPY resources /app/nhl-twitter-bot/resources/
RUN pip install --upgrade wheel
RUN pip install --upgrade setuptools
RUN pip install -qr /app/nhl-twitter-bot/requirements.txt
CMD [ "python" , "/app/nhl-twitter-bot/hockey_twitter_bot.py", "--docker" ]
