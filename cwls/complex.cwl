cwlVersion: v1.2
class: Workflow

inputs:
  start_text:
    type: string

outputs:
  result:
    type: string
    outputSource: finalize/out

steps:

  # ─────────────────────────────────────────────
  # Step 1: split input into two strings
  # ─────────────────────────────────────────────
  split:
    run:
      class: CommandLineTool
      requirements:
        CaroniRequirement:
          CaroniJobName: foojob
          CaroniJobKVs:
            foo: bar
            bar: baz
      inputs:
        text:
          type: string
          inputBinding:
            position: 1
      outputs:
        outA:
          type: string
          outputBinding:
            glob: a.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())
        outB:
          type: string
          outputBinding:
            glob: b.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())
    in:
      text: start_text
    out: [outA, outB]

  # ─────────────────────────────────────────────
  # Step 2A: process branch A
  # ─────────────────────────────────────────────
  stepA:
    run:
      class: CommandLineTool
      baseCommand: tr
      arguments: ["a-z", "A-Z"]
      inputs:
        text:
          type: string
          inputBinding:
            position: 1
      outputs:
        out:
          type: string
          outputBinding:
            glob: stdout.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())
      stdout: stdout.txt
    in:
      text: split/outA
    out: [out]

  # ─────────────────────────────────────────────
  # Step 2B: process branch B
  # ─────────────────────────────────────────────
  stepB:
    run:
      class: CommandLineTool
      baseCommand: sed
      arguments:
        - "s/$/ (processed)/"
      inputs:
        text:
          type: string
          inputBinding:
            position: 1
      outputs:
        out:
          type: string
          outputBinding:
            glob: stdout.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())
      stdout: stdout.txt
    in:
      text: split/outB
    out: [out]

  # ─────────────────────────────────────────────
  # Step 3: join both branches
  # ─────────────────────────────────────────────
  join:
    run:
      class: CommandLineTool
      baseCommand: bash
      arguments:
        - -c
        - |
          echo "$1 | $2" > joined.txt
      inputs:
        a:
          type: string
          inputBinding:
            position: 1
        b:
          type: string
          inputBinding:
            position: 2
      outputs:
        out:
          type: string
          outputBinding:
            glob: joined.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())
    in:
      a: stepA/out
      b: stepB/out
    out: [out]

  # ─────────────────────────────────────────────
  # Step 4: finalize
  # ─────────────────────────────────────────────
  finalize:
    run:
      class: CommandLineTool
      baseCommand: echo
      inputs:
        text:
          type: string
      outputs:
        out:
          type: string
          outputBinding:
            glob: stdout.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())
      stdout: stdout.txt
    in:
      text: join/out
    out: [out]
