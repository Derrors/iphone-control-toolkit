# syntax=docker/dockerfile:1
# iphone-control-toolkit 镜像。
# 上游项目原样从锁定的源码构建(go-ios、plumesign、pymobiledevice3);
# WebDriverAgent 只能在 macOS 上编译,所以用 Appium 官方构建并校验 sha256。
# 所有版本都锁在下面的 ARG 里,升级任何一项都应是一次可审查的提交,并同步 THIRD_PARTY.md。

ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
ARG GOLANG_IMAGE=golang:1.27@sha256:2920bb124f1a2e12a1d39f0cab756ae0068441ee1da7655dec7f5e374944095b
ARG RUST_IMAGE=rust:1-trixie@sha256:09027f873d45b8ecd1dc86f1fa13b7a62b875c961f017a0e331267b350430137

# ---- go-ios:隧道、启动 WDA、签名、安装、列 App ----
FROM ${GOLANG_IMAGE} AS goios
ARG GOIOS_COMMIT=51887da850dd19f4242c58a00262d06e006839cf
RUN git init -q /src && cd /src \
 && git fetch -q --depth 1 https://github.com/danielpaulus/go-ios "${GOIOS_COMMIT}" \
 && git checkout -q FETCH_HEAD \
 && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/ios . \
 && mkdir -p /out/licenses/go-ios && cp LICENSE* /out/licenses/go-ios/

# ---- plumesign(Impactor 的命令行):Apple ID 登录、注册设备、申请描述文件 ----
FROM ${RUST_IMAGE} AS plumesign
ARG IMPACTOR_TAG=v2.7.2
ARG IMPACTOR_COMMIT=b13d99559febd63e3710dfdd0ef8cdd78d10ae13
RUN apt-get update \
 && apt-get install -y --no-install-recommends cmake clang libclang-dev pkg-config libssl-dev \
 && rm -rf /var/lib/apt/lists/*
RUN git clone -q --depth 1 -b "${IMPACTOR_TAG}" https://github.com/claration/impactor /src && cd /src \
 && test "$(git rev-parse HEAD)" = "${IMPACTOR_COMMIT}" \
 && cargo build --release --locked -p plumesign \
 && mkdir -p /out/licenses/impactor \
 && cp target/release/plumesign /out/ && strip /out/plumesign \
 && cp LICENSE /out/licenses/impactor/

# ---- WebDriverAgent:Appium 官方构建的未签名真机包,重新打成 IPA ----
FROM ${DEBIAN_IMAGE} AS wda
ARG WDA_VERSION=v16.15.3
ARG WDA_SHA256=2176793538d902f6b1e61291e9997f68d306541f222ea715d256a7c6ce9d4fc5
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip zip \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/wda.zip \
      "https://github.com/appium/WebDriverAgent/releases/download/${WDA_VERSION}/WebDriverAgentRunner-Runner.zip" \
 && echo "${WDA_SHA256}  /tmp/wda.zip" | sha256sum -c - \
 && mkdir -p /w/Payload /out/licenses/WebDriverAgent && cd /w/Payload && unzip -q /tmp/wda.zip \
 && cd /w && zip -qry /out/WDA-unsigned.ipa Payload \
 && curl -fsSL -o /out/licenses/WebDriverAgent/LICENSE \
      "https://raw.githubusercontent.com/appium/WebDriverAgent/${WDA_VERSION}/LICENSE"

# ---- Python:pymobiledevice3(从 git tag 构建)和本项目的 MCP 服务,各一个 venv ----
FROM ${DEBIAN_IMAGE} AS python
ARG PMD3_TAG=v11.49.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-dev build-essential git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY docker/constraints-pmd3.txt docker/constraints-mcp.txt /tmp/
RUN python3 -m venv /opt/pmd3 \
 && /opt/pmd3/bin/pip install --no-cache-dir -c /tmp/constraints-pmd3.txt \
      "pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@${PMD3_TAG}"
COPY pyproject.toml README.md /src/
COPY src /src/src
RUN python3 -m venv /opt/mcp \
 && /opt/mcp/bin/pip install --no-cache-dir -c /tmp/constraints-mcp.txt /src

# ---- 运行镜像 ----
FROM ${DEBIAN_IMAGE}
# usbmuxd、libimobiledevice-utils 用 Debian 的包(源码可从 Debian 获取)
RUN apt-get update \
 && apt-get install -y --no-install-recommends usbmuxd libimobiledevice-utils python3 ca-certificates curl procps \
 && rm -rf /var/lib/apt/lists/*
COPY --from=python /opt/pmd3 /opt/pmd3
COPY --from=python /opt/mcp /opt/mcp
COPY --from=goios /out/ios /usr/local/bin/ios
COPY --from=plumesign /out/plumesign /usr/local/bin/plumesign
COPY --from=wda /out/WDA-unsigned.ipa /opt/ictl/wda/WDA-unsigned.ipa
COPY --from=goios /out/licenses/ /usr/share/licenses/
COPY --from=plumesign /out/licenses/ /usr/share/licenses/
COPY --from=wda /out/licenses/ /usr/share/licenses/
COPY LICENSE THIRD_PARTY.md /usr/share/doc/iphone-control-toolkit/
COPY container/ /opt/ictl/
# 配对记录、Apple ID 登录状态、开发者镜像缓存都放进 /data,删掉重建容器不丢
RUN chmod 755 /opt/ictl/*.sh && chmod 644 /opt/ictl/lib.sh \
 && rm -rf /var/lib/lockdown && ln -s /data/lockdown /var/lib/lockdown \
 && mkdir -p /root/.config /root/.local/share \
 && ln -s /data/plume /root/.config/PlumeImpactor \
 && ln -s /data/pmd3 /root/.local/share/pymobiledevice3
ENV PATH=/opt/pmd3/bin:$PATH \
    ICTL_DATA=/data
LABEL org.opencontainers.image.title="iphone-control-toolkit" \
      org.opencontainers.image.description="Drive a real iPhone from Linux: WebDriverAgent + CoreDevice HID + MCP" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.documentation="/usr/share/doc/iphone-control-toolkit/THIRD_PARTY.md"
ENTRYPOINT ["/opt/ictl/entrypoint.sh"]
