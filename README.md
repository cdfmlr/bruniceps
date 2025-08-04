# bunting/bruniceps

> 没用的鸟类小知识: bruniceps 即 Emberiza bruniceps，褐头鹀，俗称 Red-headed bunting。

bruniceps (Bunting/Bruniceps Resource Utility for New Items Copying, Encoding, Placing and Structuring) 是一个用于下载、转码、整理剧集/电影的工具。

- bruniceps 是 bunting 系统的一部分
- bruniceps 依赖于 ffmpeg 以及 aria2c

## Install

- ffmpeg >= 6.1.1 (因为需要默认编译了 SVT-AV1)
- aria2c >= 1.37.0 (因为只测试了这个版本)
- python >= 3.13 (因为只测试了这个版本)
   - pyyaml >= 6.0.2 (因为只测试了这个版本)

```bash
apt-get install aria2 ffmpeg

git clone https://github.com/cdfmlr/bruniceps.git
cd bruniceps
python -m venv venv
./venv/bin/python -m pip install pyyaml
```

## Usage

```bash
vi bruniceps.yaml
# 按需修改配置

./venv/bin/python3 bruniceps.py sync
```

子命令：

- sync 会把配置中定义的所有单集下载下来并转码，放到指定目录下。
- （目前也只有 sync）

配置文件：

- 默认是读当前目录下的 `bruniceps.yaml`
- 说是可以用命令行选项 `-c path/to/config.yaml` 来自定义（没试过）
- 或者也许也能设置环境变量 `BRUNICEPS_CONFIG=path/to/config.yaml` 来设置
- （优先级：命令行选项 > 环境变量 > 默认的 ./bruniceps.yaml）

## TODO

TODO

## License

MIT OR Apache-2.0

