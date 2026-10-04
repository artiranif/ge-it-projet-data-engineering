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

# Install project dependencies ONLY. We do NOT reinstall apache-airflow: it is
# already provided by the base image, and reinstalling it can leave a broken
# environment (e.g. "No module named 'airflow'"). Constraints keep versions
# aligned with the ones Airflow was tested with.
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    -r /requirements.txt \
    --constraint "${HOME}/constraints.txt"
