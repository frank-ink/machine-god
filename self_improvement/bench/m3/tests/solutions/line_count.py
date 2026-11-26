import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    with open(args.filename, encoding="utf-8") as stream:
        print(sum(line.startswith(args.prefix) for line in stream))

if __name__ == "__main__":
    main()
