# bunting/bruniceps

> 没用的鸟类小知识: bruniceps 即 Emberiza bruniceps，褐头鹀，俗称 Red-headed bunting。

bruniceps (Bunting/Bruniceps Resource Utility for New Items Copying, Encoding, Placing and Structuring) 是一个用于下载、转码、整理剧集/电影的工具。

- bruniceps 是 bunting 系统的一部分
- bruniceps 依赖于 ffmpeg, aria2c 以及 pyyaml

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

- `sync`：把配置中定义的所有单集下载下来并转码，放到指定目录下。
- `dry-run`：把读到的配置（如果有多个配置文件会显示合并后的最终结果）打印出来，然后立即退出。
- （目前子命令都没有额外的选项）

配置文件：

- 默认是读当前目录下的 `bruniceps.yaml`
- 可以用命令行选项 `-c path/to/config.yaml` 来自定义
- 支持多个配置文件：`-c base.yaml,override.yaml,override2.yaml`，配置内容会深度合并，排在后面的会覆盖前面的。
- 据说也能设置环境变量 `BRUNICEPS_CONFIG=path/to/config.yaml` 来设置
- （优先级：命令行选项 > 环境变量 > 默认的 ./bruniceps.yaml）

多个配置文件的例子：

```bash
# 示例目录结构
bash$ tree config/
config/
├── meta-config.yaml
├── series-anime-2025-01.yaml
├── series-anime-2025-04.yaml
├── series-anime-2025-07.yaml
└── series-movie-2025.yaml

# 获取一个按照文件名称排序的配置列表
bash$ find config -type f -name '*.yaml' | sort | tr '\n' ','
config/meta-config.yaml,config/series-anime-2025-01.yaml,config/series-anime-2025-04.yaml,config/series-anime-2025-07.yaml,config/series-movie-2025.yaml,

# 输入到 bruniceps:
bash$ ./venv/bin/python bruniceps.py -c "$(find config -type f -name '*.yaml' | sort | tr '\n' ',')" dry-run

# dry-run 换成 sync 就会做实际的下载、转码和存放工作了。
```

## TODO

TODO

## License

MIT OR Apache-2.0

