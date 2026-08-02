import os
import re
import libcst as cst
from libcst import matchers as m

class CanonicalTransformer(cst.CSTTransformer):
    def __init__(self):
        super().__init__()
        self.deleted_modules = {
            'nexus.turn_coordinator',
            'nexus.two_node_backend',
            'nexus.nova_runtime',
            'nexus.nova_backend',
            'nexus.runtime.tool_manager',
            'nexus.tool_executor',
            'nexus.context_manager',
        }
        
        self.class_renames = {
            'Agent': 'NexusRuntime',
            'ExecutionPipeline': 'ExecutionEngine',
            'RepoGraph': 'ContextEngine',
            'RunFinalizer': 'ReportBuilder',
            'TaskDagKernel': 'ExecutionEngine',
            'ExecutionKernel': 'ExecutionEngine',
            'TurnCoordinator': 'SessionState',
        }
        
        self.module_renames = {
            'nexus.agent': 'nexus.nexus_runtime',
            'nexus.pipeline': 'nexus.execution_engine',
            'nexus.repo_graph': 'nexus.context_engine',
            'nexus.run_finalizer': 'nexus.report_builder',
            'nexus.runtime.kernel': 'nexus.execution_engine',
        }

    def leave_ImportFrom(self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom) -> cst.ImportFrom | cst.RemovalSentinel:
        if original_node.module:
            module_name = ""
            if isinstance(original_node.module, cst.Name):
                module_name = original_node.module.value
            elif isinstance(original_node.module, cst.Attribute):
                parts = []
                node = original_node.module
                while isinstance(node, cst.Attribute):
                    parts.insert(0, node.attr.value)
                    node = node.value
                if isinstance(node, cst.Name):
                    parts.insert(0, node.value)
                module_name = ".".join(parts)
            
            if module_name in self.deleted_modules:
                return cst.RemoveFromParent()
            
            if module_name in self.module_renames and module_name != 'nexus.runtime.kernel':
                new_module = self.module_renames[module_name]
                parts = new_module.split('.')
                new_attr = cst.Name(parts[0])
                for part in parts[1:]:
                    new_attr = cst.Attribute(value=new_attr, attr=cst.Name(part))
                updated_node = updated_node.with_changes(module=new_attr)

            if not isinstance(updated_node.names, cst.ImportStar):
                new_names = []
                for alias in updated_node.names:
                    name_str = alias.name.value
                    if name_str in self.class_renames:
                        pass
                    else:
                        new_names.append(alias)
                if not new_names:
                    return cst.RemoveFromParent()
                updated_node = updated_node.with_changes(names=tuple(new_names))
                
        return updated_node

    def leave_Import(self, original_node: cst.Import, updated_node: cst.Import) -> cst.Import | cst.RemovalSentinel:
        new_names = []
        for alias in updated_node.names:
            parts = []
            node = alias.name
            while isinstance(node, cst.Attribute):
                parts.insert(0, node.attr.value)
                node = node.value
            if isinstance(node, cst.Name):
                parts.insert(0, node.value)
            
            name_str = ".".join(parts)
            if name_str in self.deleted_modules:
                continue
            
            if name_str in self.module_renames and name_str != 'nexus.runtime.kernel':
                new_module = self.module_renames[name_str]
                new_parts = new_module.split('.')
                new_attr = cst.Name(new_parts[0])
                for part in new_parts[1:]:
                    new_attr = cst.Attribute(value=new_attr, attr=cst.Name(part))
                new_alias = alias.with_changes(name=new_attr)
                new_names.append(new_alias)
            else:
                new_names.append(alias)
        
        if not new_names:
            return cst.RemoveFromParent()
        
        return updated_node.with_changes(names=tuple(new_names))

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        if original_node.value in self.class_renames:
            return updated_node.with_changes(value=self.class_renames[original_node.value])
        return updated_node

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef | cst.RemovalSentinel:
        if original_node.name.value in ['ExecutionKernel', 'TaskDagKernel', 'TurnCoordinator', 'TwoNodeBackend', 'NovaRuntime', 'NovaBackend']:
            return cst.RemoveFromParent()
        return updated_node

class EmptyBlockFixer(cst.CSTTransformer):
    def _ensure_pass(self, body):
        if isinstance(body, cst.IndentedBlock):
            if not body.body:
                return body.with_changes(body=[cst.SimpleStatementLine(body=[cst.Pass()])])
        return body

    def leave_If(self, original_node: cst.If, updated_node: cst.If) -> cst.If:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))

    def leave_For(self, original_node: cst.For, updated_node: cst.For) -> cst.For:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))
        
    def leave_While(self, original_node: cst.While, updated_node: cst.While) -> cst.While:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))
        
    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))

    def leave_Try(self, original_node: cst.Try, updated_node: cst.Try) -> cst.Try:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))

    def leave_ExceptHandler(self, original_node: cst.ExceptHandler, updated_node: cst.ExceptHandler) -> cst.ExceptHandler:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))

    def leave_With(self, original_node: cst.With, updated_node: cst.With) -> cst.With:
        return updated_node.with_changes(body=self._ensure_pass(updated_node.body))


class InsertImportTransformer(cst.CSTTransformer):
    def __init__(self, imports_to_add):
        super().__init__()
        self.imports_to_add = imports_to_add

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        new_body = list(updated_node.body)
        
        insert_idx = 0
        for i, statement in enumerate(new_body):
            if isinstance(statement, cst.SimpleStatementLine):
                for node in statement.body:
                    if isinstance(node, cst.ImportFrom) and node.module and isinstance(node.module, cst.Name) and node.module.value == "__future__":
                        insert_idx = i + 1
        
        statements_to_insert = []
        for imp in self.imports_to_add:
            parts = imp.split('.')
            mod = '.'.join(parts[:-1])
            cls = parts[-1]
            mod_parts = mod.split('.')
            mod_cst = cst.Name(mod_parts[0])
            for p in mod_parts[1:]:
                mod_cst = cst.Attribute(value=mod_cst, attr=cst.Name(p))
            
            import_node = cst.SimpleStatementLine(body=[
                cst.ImportFrom(
                    module=mod_cst,
                    names=[cst.ImportAlias(name=cst.Name(cls))]
                )
            ])
            statements_to_insert.append(import_node)
            
        new_body[insert_idx:insert_idx] = statements_to_insert
        return updated_node.with_changes(body=new_body)

def process_file(path):
    with open(path, 'r') as f:
        source = f.read()
    try:
        module = cst.parse_module(source)
    except Exception as e:
        print(f"Error parsing {path}: {e}")
        return
        
    transformer = CanonicalTransformer()
    modified_module = module.visit(transformer)
    
    # Analyze if we need to add imports
    code = modified_module.code
    imports_to_add = []
    
    if 'NexusRuntime' in code and 'from nexus.nexus_runtime import NexusRuntime' not in code and 'class NexusRuntime' not in code:
        imports_to_add.append('nexus.nexus_runtime.NexusRuntime')
    if 'ExecutionEngine' in code and 'from nexus.execution_engine import ExecutionEngine' not in code and 'class ExecutionEngine' not in code:
        imports_to_add.append('nexus.execution_engine.ExecutionEngine')
    if 'ContextEngine' in code and 'from nexus.context_engine import ContextEngine' not in code and 'class ContextEngine' not in code:
        imports_to_add.append('nexus.context_engine.ContextEngine')
    if 'ReportBuilder' in code and 'from nexus.report_builder import ReportBuilder' not in code and 'class ReportBuilder' not in code:
        imports_to_add.append('nexus.report_builder.ReportBuilder')
        
    if imports_to_add:
        modified_module = modified_module.visit(InsertImportTransformer(imports_to_add))
        
    # Finally fix any empty blocks caused by deletion
    modified_module = modified_module.visit(EmptyBlockFixer())

    final_code = modified_module.code
    
    if final_code != source:
        with open(path, 'w') as f:
            f.write(final_code)

def main():
    # 1. Rename files
    renames = {
        'nexus/agent.py': 'nexus/nexus_runtime.py',
        'nexus/pipeline.py': 'nexus/execution_engine.py',
        'nexus/repo_graph.py': 'nexus/context_engine.py',
        'nexus/run_finalizer.py': 'nexus/report_builder.py',
    }
    for old, new in renames.items():
        if os.path.exists(old):
            os.rename(old, new)
            
    # Delete overlaps
    deletes = [
        'nexus/context_manager.py',
        'nexus/turn_coordinator.py',
        'nexus/two_node_backend.py',
        'nexus/nova_runtime.py',
        'nexus/nova_backend.py',
        'nexus/runtime/tool_manager.py',
        'nexus/tool_executor.py',
        'tests/test_two_node_backend.py',
        'tests/test_nova_backend.py',
        'tests/test_runtime_engine.py',
        'tests/test_engines.py',
    ]
    for d in deletes:
        if os.path.exists(d):
            os.remove(d)

    # 2. Process AST
    for root, dirs, files in os.walk('.'):
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                process_file(path)

if __name__ == '__main__':
    main()
