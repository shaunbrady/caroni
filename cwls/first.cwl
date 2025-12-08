cwlVersion: v1.2
class: Workflow

#$schemas:
#  - records.yml
$import: records.yml

requirements:
  InlineJavascriptRequirement: {}

inputs:
  initial: Stage1Record

steps:

  step1:
    run:
      class: CommandLineTool
      inputs:
        input_record: Stage1Record
      outputs:
        out_record:
          type: Stage2Record
          outputBinding:
            outputEval: |
              {
                "computed": inputs.input_record.value1 + 10,
                "passed_flag": inputs.input_record.flag
              }
      baseCommand: []
    in:
      input_record: initial
    out: [out_record]

  step2:
    run:
      class: CommandLineTool
      inputs:
        input_record: Stage2Record
      outputs:
        out_record:
          type: Stage3Record
          outputBinding:
            outputEval: |
              {
                "doubled": inputs.input_record.computed * 2,
                "original_flag": inputs.input_record.passed_flag
              }
      baseCommand: []
    in:
      input_record: step1/out_record
    out: [out_record]

  step3:
    run:
      class: CommandLineTool
      inputs:
        input_record: Stage3Record
      outputs:
        final_record:
          type: FinalRecord
          outputBinding:
            outputEval: |
              {
                "summary": "Value doubled to " + inputs.input_record.doubled,
                "flag_state": inputs.input_record.original_flag
              }
      baseCommand: []
    in:
      input_record: step2/out_record
    out: [final_record]

outputs:
  result:
    type: FinalRecord
    outputSource: step3/final_record