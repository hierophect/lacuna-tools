## Lacuna Tools

Utilities for the Lacuna language system, such as the markdown-json converter, various crude csv manipulators, and language-specific tools for generating conjugation tables and other manually challenging language tasks.

### Requirements:

- Python 3.9.4 or higher
- Language-specific tool scripts may have additional language module requirements. Check each individually.

### Instructions:

It's recommended to clone the repository directly into the folder where you are doing your deck assembly work, so these scripts are locally available.

- **parser/lacu_parse.py**: debugs a deck created in the Lacuna Markdown syntax and dumps it to json. Automatically detects linkage and deck integrity errors before dumping, and provides them line by line. Currently requires all constituent components of a deck - a dummy pairgroup must be created even if none are used. Use:

  ```
  python lacu_parse.py input.md >> output.json
  ```

- **tools/row_swapper.py**: a crude program for swapping rows of autogenerated language CSV tables, such as those obtained from vocabulary websites. Non destructive, creates a new file. Use:

  ```
  python row_swapper.py input.csv
  # Examples
  # for a 4 column file, entering 3,2,1,0 at the prompt will reverse the order of the columns
  # for a 4 column file, entering 3,1,2,0 will swap the first and final column
  ```

- **tools/truncator.py**: a crude program that cuts columns off the end of a CSV file. Non destructive, creates a new file. Use:

  ```
  python truncator.py input.csv
  ```

- **tools/verb_conjugator.py**: Japanese specific. Provides a table of Japanese conjugations when provided with the dictionary versions in the following format:
  ```
  g;行く
  i;食べる
  x;来る
  ```

  Verbs must be categorized by type: `g`, `i` and `x` stand for Godan (u verbs), Ichidan (ru verbs) and Irregular verbs, respectively. Use:
  ```
  # pip install japanese-verb-conjugator-v2
  python verb_conjugator.py input.csv >> output.csv
  ```

