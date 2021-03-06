#!env/bin/python
from llvmlite import ir
import fire


def compile(input_file=None, input_code=None, tape_length=100, output_file=None):
    if input_code:
        code = input_code
    elif input_file:
        with open(input_file, 'r') as f:
            code = f.read()
    else:
        raise Exception('No input code or file provided.')
    
    block_count = 0
    mod = ir.Module("MainModule")
    mod.triple = "arm64-apple-macosx12.0.0"
    lfunc = ir.Function(mod, ir.FunctionType(ir.IntType(8), []), "main")
    entry_block = lfunc.append_basic_block('entry')
    builder = ir.IRBuilder(entry_block)
    exit_block = builder.append_basic_block("exit")

    # Create tape
    tape = builder.alloca(ir.ArrayType(ir.IntType(8), tape_length))
    builder.store(ir.Constant(ir.ArrayType(
        ir.IntType(8), tape_length), [0] * tape_length), tape)
    # Create tape pointer
    tape_ptr = builder.gep(
        tape, [ir.Constant(ir.IntType(8), 0), ir.Constant(ir.IntType(8), 0)])

    blocks = [builder.append_basic_block(f"block{block_count}")]
    block_count+=1
    builder.branch(blocks[0])
    builder = ir.IRBuilder(blocks[0])

    for op in code:
        if op == "+":
            val_at_ptr = builder.load(tape_ptr)
            builder.store(builder.add(
                val_at_ptr, ir.Constant(ir.IntType(8), 1)), tape_ptr)
        elif op == "-":
            val_at_ptr = builder.load(tape_ptr)
            builder.store(builder.sub(
                val_at_ptr, ir.Constant(ir.IntType(8), 1)), tape_ptr)
        elif op == ">":
            tape_ptr = builder.gep(tape_ptr, [ir.Constant(ir.IntType(8), 1)])
        elif op == "<":
            tape_ptr = builder.gep(tape_ptr, [ir.Constant(ir.IntType(8), -1)])
        elif op == ".":
            # https://go.dev/src/syscall/zsysnum_darwin_arm64.go
            fty = ir.FunctionType(ir.IntType(32), [
                ir.IntType(32),  # x16 (=4)
                ir.IntType(32),  # x0 (=1)
                ir.IntType(8).as_pointer(),
                ir.IntType(32)
            ])

            # Uncomment this to make char=3 => "3"
            # char = builder.add(char, ir.Constant(ir.IntType(8), 48))
            builder.asm(fty, "svc 0", "=r,{x16},{x0},{x1},{x2}", (
                ir.IntType(32)(4),
                ir.IntType(32)(1),
                tape_ptr,
                ir.IntType(32)(1)
            ), True, name="print")

        elif op == "e":
            builder.asm(ir.FunctionType(ir.IntType(32),
                                        [ir.IntType(32), ir.IntType(32)]),
                        "svc 0", "=r,{x0},{x16}", [ir.IntType(32)(0), ir.IntType(32)(1)], True, name="exit")
        elif op == "[":
            # Create a new block
            # Make the current block branch to the new block
            blocks.append(builder.append_basic_block(f"block{block_count}_open"))
            block_count+=1
            builder.branch(blocks[-1])
            builder = ir.IRBuilder(blocks[-1])
        elif op == "]":
            # Create a new block
            # Make the current block branch to the new block if the value at the current pointer is 0
            val_at_ptr = builder.load(tape_ptr)
            branch_condition = builder.icmp_signed(
                '==', val_at_ptr, ir.Constant(ir.IntType(8), 0))
            open_block = blocks.pop()
            close_block = builder.append_basic_block(
                open_block.name.replace("open", "close"))
            builder.cbranch(branch_condition, close_block, open_block)
            builder = ir.IRBuilder(close_block)

    # Exit block
    # This block returns the value at the tape pointer
    builder = ir.IRBuilder(exit_block)
    ret = builder.load(tape_ptr)
    builder.ret(ret)

    # Make the last block branch to the exit block
    if not blocks[-1].is_terminated:
        builder.position_at_end(blocks[-1])
    else:
        builder.position_at_end(close_block)

    builder.branch(exit_block)

    if output_file:
        with open(output_file, "w") as f:
            f.write(str(mod))
    else:
        print(mod)

if __name__=="__main__":
    fire.Fire(compile)