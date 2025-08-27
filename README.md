# bunting/bruniceps

> 没用的鸟类小知识: bruniceps 即 Emberiza bruniceps，褐头鹀，俗称 Red-headed bunting。

bruniceps (Bunting/Bruniceps Resource Utility for New Items Copying, Encoding, Placing and Structuring) 是一个用于下载、转码、整理剧集/电影的工具。

- bruniceps 是 bunting 系统的一部分
- bruniceps 依赖于 ffmpeg（包括 ffprobe）, aria2c 以及 pyyaml

## Install

- ffmpeg >= 6.1.1 (因为需要默认编译了 SVT-AV1)
  - ffprobe (通常应该是和 ffmpeg 一起安装的，无需单独安装)
- aria2c >= 1.37.0 (因为只测试了这个版本)
- python >= 3.13 (因为只测试了这个版本)
   - pyyaml >= 6.0.2 (因为只测试了这个版本)

```bash
brew install aria2 ffmpeg

git clone https://github.com/cdfmlr/bruniceps.git
cd bruniceps
python -m venv venv
./venv/bin/python -m pip install pyyaml
```

## Usage

```bash
cp example-config.yaml bruniceps.yaml
vi bruniceps.yaml  # 按需修改配置

./venv/bin/python3 bruniceps.py sync  # 运行，按照配置定义，执行 下载、转码、存放 的操作
```

### 子命令

- `sync`：把配置中定义的所有单集下载下来并转码，放到指定目录下。
- `dry-run`：把读到的配置（如果有多个配置文件会显示合并后的最终结果）打印出来，然后立即退出。
- （目前子命令都没有额外的选项）

### 配置文件

- 默认是读当前目录下的 `bruniceps.yaml`
  - 配置内容可以参考 [example-config.yaml](example-config.yaml)
- 可以用命令行选项 `-c path/to/config.yaml` 来自定义
  - 支持多个配置文件：`-c base.yaml,override.yaml,override2.yaml`，配置内容会深度合并，排在后面的会覆盖前面的。
  - 支持配置目录：-c 列表中如果有目录，将会被递归遍历，其下所有 YAML 文件均会被当作配置文件，按字符排序，替代掉目录在 -c 列表中的位置。
- 据说也能设置环境变量 `BRUNICEPS_CONFIG=path/to/config.yaml` 来设置
- （优先级：命令行选项 > 环境变量 > 默认的 ./bruniceps.yaml）

#### 最小必要配置

```yaml
meta:
  catalogs:
    tv:  # 至少需要一个 catalog，并指定一个目标目录（即最终存放视频文件的位置）
      dir: "/path/to/tv"

series:
  konoSubaS03:  # 一个简短的名字作为 key，这个只是 程序区分系列 + 显示日志用的
    title: "Kono Subarashii Sekai ni Shukufuku wo"  # 这个是实际的正式名字，目录和文件名会用这个
    catalog: tv  # series 放到 catalog 里
    episodes:
      - key: S03E01  # 区分单集的，infuse 之类的软件都认识这种后缀
        source: "magnet:..."  # 下载地址，一般用 magnet
        # 这一集处理完最终会放到 "/path/to/tv"/"Kono Subarashii Sekai ni Shukufuku wo"/"Kono Subarashii Sekai ni Shukufuku wo S03E01.mkv"
      - key: S03E02  # 另一集
        source: "magnet:..."
  monoS01:  # 另一个 series
    title: "mono"
    catalog: tv
    episodes:
      - key: S01E01
        source: "magnet:..."
```

#### 配置概念与指南

一些概念：

- 层次结构：
  - *catalogs*：一个 catalog 包含多个 series，相当于是添加到 infuse/emby/jellyfin 们的一个源。catalog 一般是 tv, anime, movie 这种抽象的
    - *series*：一个 series 就是一个剧/番/电影，一个 series 必须放到某个 catalog 中，一个 series 可以包含很多季
      - *episodes*：一个 episode 就是一个 series 中某一季的某一单集，其 `key` 一般命名为这集的季数+集数：例如 `S01E12` 是第 1 季、第 12 集，如果是电影 `key` 就随便写点什么 `[1080p][en_US]` 之类的片源信息吧（但不能为空）
- 配置文件中，包含两个顶层部分：meta 和 series
  - **meta** 中配置 catalogs 和其他基础的自定义信息，例如自定义 ffmpeg 命令等
  - **series** 是一个字典（dict/map/object/...），不是列表（list/array/slice/...）
- 下载并编码处理完成的单集最终会放到 `{catalog.dir}/{series.title}/"{series.title} {episode.key}.mkv|mp4"`
  - mkv 还是 mp4 取决于下载到的文件格式，也可以参考 [example-config.yaml](example-config.yaml) ，配合使用 `meta.encoding_profiles` 和 `series.episodes.format` 进行高级自定义重载，转成任意格式。
- bruniceps 默认没有季（season）的概念，也不用目录来区分 series 中的季。因为我发觉很多时候仅依靠集的 `S??E??` 标识就足够了，加一层目录访问起来还多点两下麻烦。
  - 如果真的需要 season，可以参考 [example-config.yaml](example-config.yaml) ，配合 `series.dir` 或 `episode.dir` 进行目录重载来达到区分季的目的；
  - 或者也可以转换思路，把整个系列作为一个 catalog，把每个 season 作为 catalog 下的一个 series，也能达到一样的效果。

#### 多个配置

如果需要多个配置文件，推荐整理到一个目录中，这样命令写起来比较方便，例如：

```bash
# 示例目录结构
bash$ tree config/
config/
├── meta-config.yaml           # 包含 meta: 的配置，定义 catalogs
├── series-anime-2025-01.yaml  # 包含 series:
├── series-anime-2025-04.yaml  # 同样包含 series:
├── series-anime-2025-07.yaml  # 半年番/更长的系列: 推荐统一写在最初开始文件中就行，虽然可以但不推荐拆到多个文件中（毕竟是支持深度合并的，主要是像我这种猪脑容易过载，如果能弄得清就随意了）
└── series-movie-2025.yaml

# 将配置目录输入到 bruniceps:
bash$ ./venv/bin/python bruniceps.py -c config dry-run

# dry-run 换成 sync 就会做实际的下载、转码和存放工作了。
```

## TODO

TODO

## License

MIT OR Apache-2.0

