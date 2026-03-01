# Protocol file

The file is taken from
https://github.com/Turasa/libsignal-service-java/blob/master/service/src/main/protowire/SignalService.proto

The current `libsignal-service-java` version is `v2.15.3_unofficial_140`.

To find the version for a given `signal-cli-rest-api` version:
1. Check the `signal-cli` version used `signal-cli-rest-api`'s [Docker file](https://github.com/bbernhard/signal-cli-rest-api/blob/1129e5a7bec43c90dc0631b8090a7ea590bcf082/Dockerfile#L3)
2. Check the `libsignal-service-java` version in `signal-cli`'s [lib.versions.toml](https://github.com/AsamK/signal-cli/blob/af56a28b944991fbcaf5b52853671a0c56be0af2/gradle/libs.versions.toml#L15)

Regenerate the files with
```bash
uv run python -m grpc.tools.protoc -I . --python_betterproto2_opt=pydantic_dataclasses --python_betterproto2_out=lib ./SignalService.proto
```

THE MESSAGES ARE NOT ACTUALLY DEFINED THERE BUT IN EACH CLASS IN https://github.com/AsamK/signal-cli/blob/master/src/main/java/org/asamk/signal/json
