FROM ubuntu:20.04
MAINTAINER Artificien artificien1@gmail.com

# Install system packages
RUN apt update
RUN apt install -y curl python3-pip python3-dev build-essential libssl-dev libffi-dev python3-setuptools gunicorn

# Install Node
ENV NODE_VERSION=14.2.0
RUN curl -o- https://raw.githubusercontent.com/creationix/nvm/v0.34.0/install.sh | bash
ENV NVM_DIR=/root/.nvm
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm use v${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm alias default v${NODE_VERSION}
ENV PATH="/root/.nvm/versions/node/v${NODE_VERSION}/bin/:${PATH}"

# Install AWS CDK
ENV AWS_DEFAULT_REGION=us-east-1
RUN npm install -g aws-cdk

# Copy code in and run it
COPY entrypoint.sh requirements.txt /app/
WORKDIR /app/
RUN pip3 install -r requirements.txt
COPY /src /app/src
ENTRYPOINT ["sh", "entrypoint.sh"]
