FROM gitpod/workspace-full

# Install Java 11 (required for Flink)
RUN bash -c ". /home/gitpod/.sdkman/bin/sdkman-init.sh && sdk install java 11.0.24-tem"

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh