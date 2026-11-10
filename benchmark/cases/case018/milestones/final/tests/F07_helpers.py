# feature: F07
"""Compile real native inputs and expose their public symbol addresses."""
from _helpers import require_tools, run_command, import_product


def execution_program(directory):
    source = directory / 'F07.S'
    source.write_text('''
.text
.global _start, compute, branch, indirect, forever, terminate, stop1, stop2, finished
_start:
    mov (%rdi), %rax
    add %rsi, %rax
    xor $0x35, %rax
    mov %rax, (%rdi)
    cmp $20, %rax
    ja high
    sub $3, %rax
    jmp invoke
high:
    add $9, %rax
invoke:
    call twice
finished:
    jmp finished
twice:
    shl $1, %rax
    ret
compute:
    lea (%rdi,%rsi,2), %rax
    ret
branch:
    test %rdi, %rdi
    jz zero
    mov $17, %eax
    ret
zero:
    mov $29, %eax
    ret
indirect:
    jmp *%rax
forever:
    jmp forever
terminate:
    mov $60, %eax
    xor %edi, %edi
    syscall
.global limits
limits:
    add $3, %rax
stop1:
    xor $0x55, %rax
stop2:
    sub $7, %rax
    ret
.section .note.GNU-stack,"",@progbits
''')
    binary = directory / 'F07.elf'
    result = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie', '-o', binary, source])
    assert result.returncode == 0, result.stderr
    project = import_product().Project(str(binary), auto_load_libs=False)
    return project


def symbol_address(project, name):
    return project.loader.find_symbol(name).rebased_addr


def java_native_program(directory):
    """Emit JVM classfile bytecode and compile a real JNI library offline.

    This small fixture needs no Java compiler; the classfile is a program input,
    not a replacement for any execution engine.
    """
    import struct
    import zipfile
    u2 = lambda n: struct.pack('>H', n)
    u4 = lambda n: struct.pack('>I', n)
    pool = []

    def utf(text):
        encoded = text.encode()
        pool.append(b'\x01' + u2(len(encoded)) + encoded)
        return len(pool)

    def cls(text):
        index = utf(text)
        pool.append(b'\x07' + u2(index))
        return len(pool)

    def member(tag, owner, name, signature):
        ni, si = utf(name), utf(signature)
        pool.append(b'\x0c' + u2(ni) + u2(si))
        nt = len(pool)
        pool.append(bytes([tag]) + u2(owner) + u2(nt))
        return len(pool)

    this, parent = cls('F07Java'), cls('java/lang/Object')
    init_parent = member(10, parent, '<init>', '()V')
    init_this = member(10, this, '<init>', '()V')
    field = member(9, this, 'value', 'I')
    saved_object = member(9, this, 'savedObject', 'LF07Java;')
    saved_array = member(9, this, 'savedArray', '[I')
    adjust = member(10, this, 'adjust', '(I)I')
    native = member(10, this, 'mutate', '(LF07Java;[II)I')
    code_name = utf('Code')
    field_name, int_signature = utf('value'), utf('I')
    saved_object_name, object_signature = utf('savedObject'), utf('LF07Java;')
    saved_array_name, array_signature = utf('savedArray'), utf('[I')
    methods = []

    def method(flags, name, signature, code=None, stack=0, locals_=0):
        ni, si = utf(name), utf(signature)
        header = u2(flags) + u2(ni) + u2(si)
        if code is None:
            methods.append(header + u2(0))
        else:
            body = u2(stack) + u2(locals_) + u4(len(code)) + code + u2(0) + u2(0)
            methods.append(header + u2(1) + u2(code_name) + u4(len(body)) + body)

    method(1, '<init>', '()V', b'\x2a\xb7' + u2(init_parent) + b'\xb1', 1, 1)
    method(9, 'main', '([Ljava/lang/String;)V', b'\xb1', 0, 1)
    # if (x > 5) return x*2; else return x-1;
    method(9, 'adjust', '(I)I', b'\x1a\x08\xa4\x00\x07\x1a\x05\x68\xac\x1a\x04\x64\xac', 2, 1)
    method(0x109, 'mutate', '(LF07Java;[II)I')
    # x=adjust(x); o=new F07Java(); o.value=x; a=new int[2];
    # a[0]=x+3; r=mutate(o,a,x); return r+o.value+a[1];
    code = (b'\x1a\xb8' + u2(adjust) + b'\x3b\xbb' + u2(this)
            + b'\x59\xb7' + u2(init_this) + b'\x4c\x2b\xb3' + u2(saved_object) + b'\x2b\x1a\xb5' + u2(field)
            + b'\x05\xbc\x0a\x4d\x2c\xb3' + u2(saved_array) + b'\x2c\x03\x1a\x06\x60\x4f'
            + b'\x2b\x2c\x1a\xb8' + u2(native) + b'\x3e\x1d\x2b\xb4' + u2(field)
            + b'\x60\x2c\x04\x2e\x60\xac')
    method(9, 'run', '(I)I', code, 4, 4)
    data = (b'\xca\xfe\xba\xbe' + u2(0) + u2(49) + u2(len(pool)+1) + b''.join(pool)
            + u2(0x21) + u2(this) + u2(parent) + u2(0)
            + u2(3) + u2(1) + u2(field_name) + u2(int_signature) + u2(0)
            + u2(9) + u2(saved_object_name) + u2(object_signature) + u2(0)
            + u2(9) + u2(saved_array_name) + u2(array_signature) + u2(0)
            + u2(len(methods)) + b''.join(methods) + u2(0))
    archive = directory / 'F07Java.jar'
    with zipfile.ZipFile(archive, 'w') as jar:
        jar.writestr('F07Java.class', data)
        jar.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nMain-Class: F07Java\n\n')
    source = directory / 'F07_jni.c'
    source.write_text('''
/* JNI table indices and signatures follow the published JNI interface. */
typedef void *Ref;
typedef const void **Env;
int Java_F07Java_mutate(Env *env, Ref klass, Ref object, Ref array, int x) {
    Ref c = ((Ref (*)(Env *,Ref))(*env)[31])(env,object);
    Ref field = ((Ref (*)(Env *,Ref,const char *,const char *))(*env)[94])(env,c,"value","I");
    int old = ((int (*)(Env *,Ref,Ref))(*env)[100])(env,object,field);
    ((void (*)(Env *,Ref,Ref,int))(*env)[109])(env,object,field,old+4);
    int element;
    ((void (*)(Env *,Ref,int,int,int *))(*env)[203])(env,array,0,1,&element);
    element += 7;
    ((void (*)(Env *,Ref,int,int,const int *))(*env)[211])(env,array,1,1,&element);
    return x*3;
}
''')
    library = directory / 'libF07.so'
    result = run_command([require_tools('gcc')['gcc'], '-shared', '-fPIC', '-nostdlib', '-o', library, source])
    assert result.returncode == 0, result.stderr
    return archive, library
