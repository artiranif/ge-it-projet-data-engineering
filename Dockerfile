# Custom Airflow image: extends the official image and installs the project
# dependencies listed in requirements.txt ONCE, at build time.
#
# Why not "_PIP_ADDITIONAL_REQUIREMENTS"? That Compose-only mechanism is a
# development/test feature: it reinstalls packages on every container start,
# ignores constraints and cannot read requirements.txt. Building a dedicated
# image (official recommended approach) is reproducible and faster at runtime.
#
# ref: https://airflow.apache.org/docs/docker-stack/build.html

FROM apache/airflow:3.3.2

# Install project dependencies. Pinning apache-airflow to the image version and
# using the constraints shipped in the image avoids a surprise downgrade/upgrade
# of Airflow or of its own dependencies.
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /requirements.txt \
    --constraint "${HOME}/constraints.txt"
