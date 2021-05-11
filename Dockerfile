# Build Pype docker image
FROM centos:7 AS builder
ARG OPENPYPE_PYTHON_VERSION=3.7.10

LABEL org.opencontainers.image.name="pypeclub/openpype"
LABEL org.opencontainers.image.title="OpenPype Docker Image"
LABEL org.opencontainers.image.url="https://openpype.io/"
LABEL org.opencontainers.image.source="https://github.com/pypeclub/pype"

USER root

# update base
RUN yum -y install deltarpm \
    && yum -y update \
    && yum clean all

# add tools we need
RUN yum -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm \
    && yum -y install centos-release-scl \
    && yum -y install \
        bash \
        which \
        git \
        devtoolset-7-gcc* \
        make \
        cmake \
        curl \
        wget \
        gcc \
        zlib-devel \
        bzip2 \
        bzip2-devel \
        readline-devel \
        sqlite sqlite-devel \
        openssl-devel \
        tk-devel libffi-devel \
        qt5-qtbase-devel \
        patchelf \
    && yum clean all

RUN mkdir /opt/openpype
# RUN useradd -m pype
# RUN chown pype /opt/openpype
# USER pype

RUN curl https://pyenv.run | bash
ENV PYTHON_CONFIGURE_OPTS --enable-shared

RUN echo 'export PATH="$HOME/.pyenv/bin:$PATH"'>> $HOME/.bashrc \
    && echo "alias pyhon3='python'" >> $HOME/.bashrc \
    && echo 'eval "$(pyenv init -)"' >> $HOME/.bashrc \
    && echo 'eval "$(pyenv virtualenv-init -)"' >> $HOME/.bashrc \
    && echo -e "eval \"$(pyenv init --path)\"\n$(cat $HOME/.profile)" > $HOME/.profile
RUN source $HOME/.bashrc && pyenv install ${OPENPYPE_PYTHON_VERSION}

COPY . /opt/openpype/
# USER root
# RUN chown -R pype /opt/openpype
RUN chmod +x /opt/openpype/tools/create_env.sh && chmod +x /opt/openpype/tools/build.sh

# USER pype

WORKDIR /opt/openpype

RUN cd /opt/openpype \
    && source $HOME/.bashrc \
    && pyenv local ${OPENPYPE_PYTHON_VERSION}

RUN source $HOME/.bashrc \
    cd /opt/openpype \
    && ./tools/create_env.sh

RUN source $HOME/.bashrc \
    cd /opt/openpype \
    && ./tools/fetch_thirdparty_libs.sh

RUN source $HOME/.bashrc \
    cd /opt/openpype \
    && bash ./tools/build.sh

RUN cd /opt/openpype \
    rm -rf ./vendor/bin
