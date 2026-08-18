FROM python:3.12-slim

RUN useradd --create-home --shell /usr/sbin/nologin ag

COPY harness/ /opt/harness/
COPY run.sh /opt/run.sh
RUN chmod +x /opt/run.sh

WORKDIR /grade
ENTRYPOINT ["/opt/run.sh"]
