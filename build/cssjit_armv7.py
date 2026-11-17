#!/usr/bin/env python3
"""Applies the ARMv7 (Thumb-2) port of the CSS selector JIT to a WebKit 2.52.6 tree (run inside the
wpe-br container against the build directory). The diff against the tarball becomes patch 0015."""
import sys

root = sys.argv[1]


def edit(path, old, new, count=1):
    full = f"{root}/{path}"
    s = open(full).read()
    assert s.count(old) == count, (path, old[:60], s.count(old))
    open(full, "w").write(s.replace(old, new))


edit("Source/WTF/wtf/PlatformEnable.h",
     "#if !defined(ENABLE_CSS_SELECTOR_JIT) && ((CPU(X86_64) || CPU(ARM64)) && ENABLE(JIT))",
     "#if !defined(ENABLE_CSS_SELECTOR_JIT) && ((CPU(X86_64) || CPU(ARM64) || (CPU(ARM_THUMB2) && HAVE(ARM_IDIV_INSTRUCTIONS))) && ENABLE(JIT))")

# Registers: r6 (addressTempRegister) and ip (dataTempRegister) belong to the MacroAssembler, r7 is the
# Thumb frame pointer, sp/lr/pc are special. r0-r3 are argument/caller-saved, the rest callee-saved.
edit("Source/WebCore/cssjit/RegisterAllocator.h",
     "#else\n#error RegisterAllocator has no defined registers for the architecture.",
     """#elif CPU(ARM_THUMB2)
static constexpr std::array<JSC::MacroAssembler::RegisterID, 4> callerSavedRegisters {
    JSC::ARMRegisters::r0,
    JSC::ARMRegisters::r1,
    JSC::ARMRegisters::r2,
    JSC::ARMRegisters::r3,
};
static constexpr std::array<JSC::MacroAssembler::RegisterID, 6> calleeSavedRegisters {
    JSC::ARMRegisters::r4,
    JSC::ARMRegisters::r5,
    JSC::ARMRegisters::r8,
    JSC::ARMRegisters::r9,
    JSC::ARMRegisters::r10,
    JSC::ARMRegisters::r11,
};
// Only used for three register-to-register moves (swapping call arguments), which never touch the
// MacroAssembler's own scratch use of ip.
static const JSC::MacroAssembler::RegisterID tempRegister = JSC::ARMRegisters::ip;
#else
#error RegisterAllocator has no defined registers for the architecture.""")
edit("Source/WebCore/cssjit/RegisterAllocator.h",
     "#else\n#error RegisterAllocator does not define the valid register range for the current architecture.",
     """#elif CPU(ARM_THUMB2)
        return (registerID >= JSC::ARMRegisters::r0 && registerID <= JSC::ARMRegisters::r5)
            || (registerID >= JSC::ARMRegisters::r8 && registerID <= JSC::ARMRegisters::r11);
#else
#error RegisterAllocator does not define the valid register range for the current architecture.""")
edit("Source/WebCore/cssjit/RegisterAllocator.h",
     "#else\n#error RegisterAllocator does not define the valid caller saved register range for the current architecture.",
     """#elif CPU(ARM_THUMB2)
        return registerID >= JSC::ARMRegisters::r0 && registerID <= JSC::ARMRegisters::r3;
#else
#error RegisterAllocator does not define the valid caller saved register range for the current architecture.""")

# AAPCS wants sp 8-byte aligned at calls; pushes here are 4 bytes and nothing else is on the stack
# at entry (the return address stays in lr).
edit("Source/WebCore/cssjit/StackAllocator.h",
     """    void alignStackPreFunctionCall()
    {
#if CPU(X86_64)""",
     """    void alignStackPreFunctionCall()
    {
#if CPU(ARM_THUMB2)
        RELEASE_ASSERT(!m_hasFunctionCallPadding);
        if (m_offsetFromTop % 8) {
            m_hasFunctionCallPadding = true;
            m_assembler.addPtrNoFlags(JSC::MacroAssembler::TrustedImm32(-stackUnitInBytes()), JSC::MacroAssembler::stackPointerRegister);
        }
#elif CPU(X86_64)""")
edit("Source/WebCore/cssjit/StackAllocator.h",
     """    void unalignStackPostFunctionCall()
    {
#if CPU(X86_64)""",
     """    void unalignStackPostFunctionCall()
    {
#if CPU(X86_64) || CPU(ARM_THUMB2)""")

sc = "Source/WebCore/cssjit/SelectorCompiler.cpp"
# r6 is callee-saved in the AAPCS and the MacroAssembler clobbers it as addressTempRegister.
edit(sc, """inline void SelectorCodeGenerator::pushMacroAssemblerRegisters()
{
}

inline void SelectorCodeGenerator::popMacroAssemblerRegisters(StackAllocator&)
{
}""", """inline void SelectorCodeGenerator::pushMacroAssemblerRegisters()
{
#if CPU(ARM_THUMB2)
    Vector<JSC::MacroAssembler::RegisterID, 1> macroAssemblerRegisters({ JSC::ARMRegisters::r6 });
    m_macroAssemblerRegistersStackReferences = m_stackAllocator.push(macroAssemblerRegisters);
#endif
}

inline void SelectorCodeGenerator::popMacroAssemblerRegisters(StackAllocator& stackAllocator)
{
#if CPU(ARM_THUMB2)
    Vector<JSC::MacroAssembler::RegisterID, 1> macroAssemblerRegisters({ JSC::ARMRegisters::r6 });
    stackAllocator.pop(m_macroAssemblerRegistersStackReferences, macroAssemblerRegisters);
#else
    UNUSED_PARAM(stackAllocator);
#endif
}""")
# Calls to C++ helpers clobber lr, so it is saved like ARM64 saves lr/fp.
edit(sc, """    m_prologueStackReferences = m_stackAllocator.push(prologueRegisters);
    return true;
#elif CPU(X86_64) && CSS_SELECTOR_JIT_DEBUGGING""", """    m_prologueStackReferences = m_stackAllocator.push(prologueRegisters);
    return true;
#elif CPU(ARM_THUMB2)
    Vector<JSC::MacroAssembler::RegisterID, 2> prologueRegisters;
    prologueRegisters.append(JSC::ARMRegisters::lr);
    prologueRegisters.append(JSC::ARMRegisters::r7);
    m_prologueStackReferences = m_stackAllocator.push(prologueRegisters);
    return true;
#elif CPU(X86_64) && CSS_SELECTOR_JIT_DEBUGGING""")
edit(sc, """    stackAllocator.pop(m_prologueStackReferences, prologueRegisters);
#elif CPU(X86_64) && CSS_SELECTOR_JIT_DEBUGGING""", """    stackAllocator.pop(m_prologueStackReferences, prologueRegisters);
#elif CPU(ARM_THUMB2)
    Vector<JSC::MacroAssembler::RegisterID, 2> prologueRegisters({ JSC::ARMRegisters::lr, JSC::ARMRegisters::r7 });
    stackAllocator.pop(m_prologueStackReferences, prologueRegisters);
#elif CPU(X86_64) && CSS_SELECTOR_JIT_DEBUGGING""")
# Thumb-2 SDIV exists on the C1's Cortex-A55 (ARMv8 AArch32); the JIT is only enabled when the build
# targets a core with it (HAVE(ARM_IDIV_INSTRUCTIONS), e.g. -mcpu=cortex-a55, not cortex-a9).
edit(sc, """    return m_assembler.branchSub32(condition, inputDividend, resultRegister, resultRegister);
#elif CPU(X86_64)""", """    return m_assembler.branchSub32(condition, inputDividend, resultRegister, resultRegister);
#elif CPU(ARM_THUMB2)
    LocalRegister divisorRegister(m_registerAllocator);
    m_assembler.move(Assembler::TrustedImm32(divisor), divisorRegister);

    LocalRegister resultRegister(m_registerAllocator);
    m_assembler.m_assembler.sdiv<32>(resultRegister, inputDividend, divisorRegister);
    m_assembler.mul32(divisorRegister, resultRegister);
    return m_assembler.branchSub32(condition, inputDividend, resultRegister, resultRegister);
#elif CPU(X86_64)""")
# 10 allocatable registers here (12 on x86_64, 16 on ARM64): a selector that needs more stays with
# the C++ SelectorChecker instead of tripping the allocator.
edit(sc, """inline SelectorCompilationStatus SelectorCodeGenerator::compile(JSC::MacroAssemblerCodeRef<JSC::CSSSelectorPtrTag>& codeRef)
{
    switch (m_functionType) {""", """inline SelectorCompilationStatus SelectorCodeGenerator::compile(JSC::MacroAssemblerCodeRef<JSC::CSSSelectorPtrTag>& codeRef)
{
    if (m_functionType == FunctionType::SimpleSelectorChecker || m_functionType == FunctionType::SelectorCheckerWithCheckingContext) {
        computeBacktrackingMemoryRequirements(m_selectorFragments);
        if (m_selectorFragments.registerRequirements > maximumRegisterCount)
            return SelectorCompilationStatus::CannotCompile;
    }

    switch (m_functionType) {""")
print("ok")
