import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';

@Injectable()
export class ReadOnlyGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const method = request.method;
    // Allow only safe read methods
    return method === 'GET' || method === 'HEAD' || method === 'OPTIONS';
  }
}
