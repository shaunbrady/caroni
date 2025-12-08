cwlVersion: v1.2
class: Workflow

$namespaces:
  caroni: https://caroni.example/cwl#

inputs:
  start_message:
    type: string

outputs:
  result:
    type: string
    outputSource: step3/out

steps:
  step1:
    run:
      class: CommandLineTool
      hints:
        caroni:CaroniRequirement:
          CaroniJobName: foojob0

      inputs:
        message:
          type: string

      outputs:
        out:
          type: string
          outputBinding:
            glob: output.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())

      stdout: output.txt

    in:
      message: start_message
    out: [out]

  step2:
    run:
      class: CommandLineTool
      hints:
        caroni:CaroniRequirement:
          CaroniJobName: foojob1

      inputs:
        text:
          type: string
          inputBinding:
            position: 1

      outputs:
        out:
          type: string
          outputBinding:
            glob: output.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())

      stdout: output.txt

    in:
      text: step1/out
    out: [out]

  step3:
    run:
      class: CommandLineTool
      hints:
        caroni:CaroniRequirement:
          CaroniJobName: foojob2

      inputs:
        final_text:
          type: string

      outputs:
        out:
          type: string
          outputBinding:
            glob: output.txt
            loadContents: true
            outputEval: $(self[0].contents.trim())

      stdout: output.txt

    in:
      final_text: step2/out
    out: [out]