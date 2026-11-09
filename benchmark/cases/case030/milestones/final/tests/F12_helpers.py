# feature: F12
"""Real native-library inputs and public wrapping/translation observations."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import run_command, run_python, write_text
from F03_helpers import ConfigurationSession, require_success
from F04_helpers import require_native_failure
from F00_candidate import require_native_program

NATIVE = '''module native_api
use iso_c_binding, only: i64 => c_int64_t, f64 => c_double
implicit none
type :: NativeMeter
 integer(i64) :: tally_value
contains
 procedure :: create
 procedure :: free
 procedure :: advance
 procedure :: read_value
 procedure :: scale
end type
contains
function native_score(x,y) result(z)
 integer(i64), intent(in) :: x,y
 integer(i64) :: z
 z = 3*x - 2*y + 11
end function
subroutine native_pair(a,b,x,y)
 integer(i64), intent(out) :: a,b
 integer(i64), intent(in) :: x,y
 a = x+y
 b = x-2*y
end subroutine
subroutine native_update(a)
 real(f64), intent(inout) :: a(:,:)
 integer :: i,j
 do j=1,size(a,2)
  do i=1,size(a,1)
   a(i,j) = 2*a(i,j) + 10*i + j
  end do
 end do
end subroutine
function native_integer(x) result(z)
 integer(i64), intent(in) :: x
 integer(i64) :: z
 z = x*4+3
end function
function native_real(x) result(z)
 real(f64), intent(in) :: x
 real(f64) :: z
 z = x*2-0.5_f64
end function
subroutine create(this,start)
 class(NativeMeter), intent(inout) :: this
 integer(i64), intent(in) :: start
 this%tally_value=start
end subroutine
subroutine free(this)
 class(NativeMeter), intent(inout) :: this
 this%tally_value=0
end subroutine
subroutine advance(this,step)
 class(NativeMeter), intent(inout) :: this
 integer(i64), intent(in) :: step
 this%tally_value=this%tally_value+3*step
end subroutine
function read_value(this) result(z)
 class(NativeMeter), intent(in) :: this
 integer(i64) :: z
 z=this%tally_value+7
end function
subroutine scale(this,factor)
 class(NativeMeter), intent(inout) :: this
 integer(i64), intent(in) :: factor
 this%tally_value=this%tally_value*factor
end subroutine
end module
'''

STUB = '''#$ header metavar includes="."
#$ header metavar libraries="native_api"
#$ header metavar libdirs="."
from zelvori.decorators import low_level
from typing import overload
@low_level('native_score')
def score(x: int, y: int) -> int: ...
@low_level('native_pair')
def pair(x: int, y: int) -> tuple[int, int]: ...
@low_level('native_update')
def update(a: 'float[:,:](order=F)') -> None: ...
@low_level('native_integer')
@overload
def select(x: int) -> int: ...
@low_level('native_real')
@overload
def select(x: float) -> float: ...
@low_level('NativeMeter')
class Meter:
    tally_value: int
    @low_level('create')
    def __init__(self, start: int) -> None: ...
    @low_level('free')
    def __del__(self) -> None: ...
    @low_level('advance')
    def move(self, step: int) -> None: ...
    @low_level('read_value')
    @property
    def value(self) -> int: ...
    @low_level('scale')
    def __imul__(self, factor: int) -> None: ...
'''

PROBE = '''program independent
use native_api
implicit none
integer(i64) :: p,q
real(f64) :: a(2,3)
type(NativeMeter) :: meter
integer :: i,j
print *, native_score(4_i64,-3_i64),native_score(-7_i64,5_i64)
call native_pair(p,q,9_i64,-4_i64)
print *, p,q
print *, native_integer(-3_i64),native_real(1.25_f64)
call meter%create(8_i64)
print *, meter%tally_value,meter%read_value()
call meter%advance(-2_i64)
print *, meter%tally_value,meter%read_value()
call meter%scale(4_i64)
print *, meter%tally_value,meter%read_value()
a=reshape([1._f64,4._f64,2._f64,5._f64,3._f64,6._f64],[2,3])
call native_update(a)
do i=1,2
 do j=1,3
  print *, a(i,j)
 end do
end do
call native_update(a)
do i=1,2
 do j=1,3
  print *, a(i,j)
 end do
end do
a=1._f64
call native_update(a)
print *, a(1,1),a(2,3)
end program
'''


def prepare_native(root):
    session = ConfigurationSession(root)
    source = write_text(root, 'native_api.f90', NATIVE)
    write_text(root, 'native_api.pyi', STUB)
    require_success(run_command(['gfortran', '-fPIC', '-c', source, '-o', 'native.o'], cwd=root))
    require_success(run_command(['ar', 'rcs', 'libnative_api.a', 'native.o'], cwd=root))
    probe = write_text(root, 'independent.f90', PROBE)
    require_success(run_command(['gfortran', probe, 'libnative_api.a', '-o', 'independent'], cwd=root))
    result = run_command([root / 'independent'], cwd=root)
    require_success(result)
    # This grammar belongs to our independent Fortran driver, not product diagnostics.
    oracle = [float(v) for v in result.stdout.split()]
    assert len(oracle) == 26, result.stdout
    require_success(session.command('wrap', root / 'native_api.pyi', '--language', 'fortran'))
    return session, oracle


def wrapped_values(session, source):
    result = run_python(source, cwd=session.root, env=session.env)
    require_success(result)
    return json.loads(result.stdout)


def translated_values(session, name, source, *, language='fortran'):
    path = write_text(session.root, name + '.py', source)
    require_success(session.command('compile', path, '--language', language))
    require_native_program(session.root / name)
    result = run_command([session.root / name], cwd=session.root, env=session.env)
    require_success(result)
    # The submitted client emits one numerical scalar per line.
    return [float(line) for line in result.stdout.splitlines()]


C_HEADER = '''#ifndef C_API_H
#define C_API_H
#include <stdint.h>
int64_t native_score(int64_t x, int64_t y);
int64_t native_integer(int64_t x);
double native_real(double x);
struct NativeMeter { int64_t tally_value; };
void native_create(struct NativeMeter *self, int64_t start);
void native_free(struct NativeMeter *self);
void native_advance(struct NativeMeter *self, int64_t step);
int64_t native_read(const struct NativeMeter *self);
void native_scale(struct NativeMeter *self, int64_t factor);
#endif
'''

C_NATIVE = '''#include "c_api.h"
int64_t native_score(int64_t x, int64_t y) { return 3*x - 2*y + 11; }
int64_t native_integer(int64_t x) { return 4*x + 3; }
double native_real(double x) { return 2*x - 0.5; }
void native_create(struct NativeMeter *self, int64_t start) { self->tally_value = start; }
void native_free(struct NativeMeter *self) { self->tally_value = 0; }
void native_advance(struct NativeMeter *self, int64_t step) { self->tally_value += 3*step; }
int64_t native_read(const struct NativeMeter *self) { return self->tally_value + 7; }
void native_scale(struct NativeMeter *self, int64_t factor) { self->tally_value *= factor; }
'''

C_STUB = '''#$ header metavar includes="."
#$ header metavar libraries="c_api"
#$ header metavar libdirs="."
from zelvori.decorators import low_level
from typing import overload
@low_level('native_score')
def score(x: int, y: int) -> int: ...
@low_level('native_integer')
@overload
def select(x: int) -> int: ...
@low_level('native_real')
@overload
def select(x: float) -> float: ...
@low_level('NativeMeter')
class Meter:
    tally_value: int
    @low_level('native_create')
    def __init__(self, start: int) -> None: ...
    @low_level('native_free')
    def __del__(self) -> None: ...
    @low_level('native_advance')
    def move(self, step: int) -> None: ...
    @low_level('native_read')
    @property
    def value(self) -> int: ...
    @low_level('native_scale')
    def __imul__(self, factor: int) -> None: ...
'''

C_PROBE = '''#include "c_api.h"
#include <stdio.h>
#include <inttypes.h>
static void state(struct NativeMeter *meter) {
    printf("%" PRId64 "\\n%" PRId64 "\\n", meter->tally_value, native_read(meter));
}
int main(void) {
    printf("%" PRId64 "\\n%" PRId64 "\\n", native_score(4,-3), native_score(-7,5));
    printf("%" PRId64 "\\n%.17g\\n", native_integer(-3), native_real(1.25));
    int64_t starts[] = {8, -5}, steps[] = {-2, 3}, factors[] = {4, -2};
    for (int i=0; i<2; ++i) {
        struct NativeMeter meter;
        native_create(&meter, starts[i]); state(&meter);
        native_advance(&meter, steps[i]); state(&meter);
        native_scale(&meter, factors[i]); state(&meter);
        native_free(&meter);
    }
    return 0;
}
'''


def prepare_c_native(root):
    """Build a supplied C library and measure it with an independent C caller."""
    session = ConfigurationSession(root)
    write_text(root, 'c_api.h', C_HEADER)
    source = write_text(root, 'c_api.c', C_NATIVE)
    write_text(root, 'c_api.pyi', C_STUB)
    require_success(run_command(['gcc', '-fPIC', '-c', source, '-o', 'native.o'], cwd=root))
    require_success(run_command(['ar', 'rcs', 'libc_api.a', 'native.o'], cwd=root))
    probe = write_text(root, 'independent.c', C_PROBE)
    require_success(run_command(['gcc', probe, 'libc_api.a', '-o', 'independent'], cwd=root))
    result = run_command([root / 'independent'], cwd=root)
    require_success(result)
    oracle = [float(line) for line in result.stdout.splitlines()]
    assert len(oracle) == 16, result
    require_success(session.command('wrap', root / 'c_api.pyi', '--language', 'c'))
    return session, oracle
